import base64
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import studio_tools
import video_provider


def image(color="white", size=(120, 80)):
    out=io.BytesIO()
    Image.new("RGB",size,color).save(out,"PNG")
    return out.getvalue()


@pytest.fixture
def studio(monkeypatch):
    app=FastAPI()
    api=APIRouter()
    users=SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)))
    user={"user_id":"studio-test","credits":5}
    async def current_user(): return user
    override=AsyncMock(return_value=({"base_url":"https://connect.krai.es/api/gateway/v1","name":"Selected KRAI"},"selected-model"))
    usage=AsyncMock()
    run=Mock(return_value=image())
    monkeypatch.setattr(studio_tools.providers,"run_image_edit",run)
    studio_tools.register_studio_routes(api,SimpleNamespace(users=users),current_user,override,lambda _:False,usage)
    app.include_router(api)
    return TestClient(app),users,override,usage,run


def post(client,tool="hdr",data=None):
    return client.post(f"/tools/{tool}/assist",files={"file":("photo.png",data or image(),"image/png")})


def test_hdr_uses_selected_engine_once(studio):
    client,users,override,usage,run=studio
    response=post(client)
    assert response.status_code==200
    override.assert_awaited_once_with("hdr")
    assert run.call_args.args[1]=="selected-model"
    assert run.call_count==1
    assert users.update_one.call_count==1
    assert usage.call_args.kwargs["ai_calls"]==1


def test_non_krai_rejected_before_charge(studio):
    client,users,override,_,run=studio
    override.return_value=({"base_url":"https://api.openai.com/v1"},"model")
    assert post(client).status_code==400
    users.update_one.assert_not_called()
    run.assert_not_called()


def test_failed_edit_refunds_without_provider_fallback(studio):
    client,users,_,usage,run=studio
    run.side_effect=RuntimeError("secret upstream details")
    response=post(client)
    assert response.status_code==502
    assert "secret" not in response.text
    assert run.call_count==1
    assert users.update_one.call_count==2
    assert users.update_one.call_args.args[1]["$inc"]["credits"]==1
    usage.assert_not_called()


def test_mask_photo_is_rejected_and_refunded(studio):
    client,users,_,_,run=studio
    run.return_value=image("orange")
    assert post(client,"manual").status_code==502
    assert users.update_one.call_count==2


def test_binary_mask_accepted(studio):
    client,_,_,_,run=studio
    from PIL import ImageDraw
    mask=Image.new("RGB",(120,80),"black")
    ImageDraw.Draw(mask).rectangle((30,20,80,60),fill="white")
    buffer=io.BytesIO()
    mask.save(buffer,"PNG")
    run.return_value=buffer.getvalue()
    assert post(client,"manual").status_code==200
    assert "segmentation mask" in run.call_args.args[3]


@pytest.mark.parametrize("color",["white","black"])
def test_unbounded_or_empty_mask_refunded(studio,color):
    client,users,_,_,run=studio
    run.return_value=image(color)
    assert post(client,"manual").status_code==502
    assert users.update_one.call_count==2


def test_invalid_image_never_charged(studio):
    client,users,_,_,run=studio
    assert post(client,data=b"invalid-image").status_code==400
    users.update_one.assert_not_called()
    run.assert_not_called()


def test_video_routes_selected_engine(monkeypatch):
    mp4=b"\0\0\0\x18ftypisom"+b"\0"*24
    response=Mock(status_code=200)
    response.json.return_value={"ok":True,"artifacts":[{"type":"video","data_b64":base64.b64encode(mp4).decode()}]}
    send=Mock(return_value=response)
    monkeypatch.setattr(video_provider.requests,"post",send)
    provider={"base_url":"https://connect.krai.es/api/gateway/v1","api_key":"test-only"}
    assert video_provider.run_video(provider,"selected-video",image(),"Camera forward",4,"16:9")==mp4
    payload=send.call_args.kwargs["json"]
    assert payload["engine_hint"]=="selected-video"
    assert payload["task"]=="video_generation"
    assert payload["input"]["duration"]==4


def test_video_failure_has_no_substitution(monkeypatch):
    response=Mock(status_code=200)
    response.json.return_value={"ok":True,"artifacts":[{"type":"image","data_b64":""}]}
    send=Mock(return_value=response)
    monkeypatch.setattr(video_provider.requests,"post",send)
    with pytest.raises(RuntimeError):
        video_provider.run_video({"base_url":"https://connect.krai.es/api/gateway/v1"},"video",image(),"move",3,"9:16")
    assert send.call_count==1


def test_existing_video_and_generated_clip_composition(tmp_path):
    import asyncio
    import video
    photo=tmp_path/"photo.png"
    source=tmp_path/"existing.mp4"
    output=tmp_path/"generated.mp4"
    Image.new("RGB",(320,180),"gray").save(photo)
    asyncio.run(video._make_clip({"path":str(photo),"secs":1.5,"motion":"ken_burns"},str(source),320,180))
    asyncio.run(video._make_clip({"video_path":str(source),"secs":1.5},str(output),320,180))
    for file in [source,output]:
        content=file.read_bytes()
        assert len(content)>1000 and content[4:8]==b"ftyp"
