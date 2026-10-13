import base64
import io
from unittest.mock import Mock, patch
import pytest
from PIL import Image
import providers
import video_provider as vp

NVIDIA={"base_url":"https://integrate.api.nvidia.com/v1","api_key":"test-secret"}
MP4=base64.b64encode(b"\x00\x00\x00\x18ftypmp42payload").decode()

def photo():
    out=io.BytesIO()
    Image.new("RGB",(32,24),"white").save(out,format="JPEG")
    return out.getvalue()

def response(status=200, body=None, headers=None):
    r=Mock(status_code=status, headers=headers or {})
    r.json.return_value=body or {"b64_video":MP4}
    return r

def test_nvidia_photo_contract():
    with patch.object(vp.requests,"post",return_value=response()) as post:
        assert vp.run_video(NVIDIA,vp.NVIDIA_VIDEO_MODEL,photo(),"preserve room",1.5,"9:16")[4:8]==b"ftyp"
    kw=post.call_args.kwargs
    assert post.call_args.args[0]=="https://ai.api.nvidia.com/v1/cosmos/nvidia/cosmos3-nano"
    assert kw["json"]["model_mode"]=="image2video"
    assert kw["json"]["input_reference"].startswith("data:image/jpeg;base64,")
    assert kw["json"]["resolution"]=="480_9_16"
    assert kw["json"]["num_frames"]==33
    assert kw["allow_redirects"] is False

def test_poll_never_resubmits():
    request_id="01234567-89ab-4cde-8123-456789abcdef"
    with patch.object(vp.requests,"post",return_value=response(202,headers={"NVCF-REQID":request_id})) as post, patch.object(vp.requests,"get",return_value=response()) as get, patch.object(vp.time,"sleep"):
        assert vp.run_video(NVIDIA,vp.NVIDIA_VIDEO_MODEL,photo(),"room",1.5,"16:9")[4:8]==b"ftyp"
    assert post.call_count==1
    assert get.call_args.args[0].endswith(request_id)

@pytest.mark.parametrize("status,code",[(402,"provider_credits"),(429,"provider_quota"),(504,"provider_timeout"),(422,"provider_contract")])
def test_explicit_errors_no_retry(status,code):
    with patch.object(vp.requests,"post",return_value=response(status)) as post:
        with pytest.raises(providers.ProviderRequestError) as err:
            vp.run_video(NVIDIA,vp.NVIDIA_VIDEO_MODEL,photo(),"room",1.5,"16:9")
    assert err.value.code==code
    assert post.call_count==1
    assert "test-secret" not in str(err.value)

@pytest.mark.parametrize("model",["nvidia/ai-synthetic-video-detector","nvidia/cosmos-transfer2.5-2b","wan-ai/wan2.2-animate-2-14b"])
def test_unsupported_models_do_not_submit(model):
    assert not vp.supports_video(NVIDIA,model)
    with patch.object(vp.requests,"post") as post, pytest.raises(providers.ProviderRequestError):
        vp.run_video(NVIDIA,model,photo(),"room",1.5,"16:9")
    post.assert_not_called()

def test_result_download_never_sends_api_key():
    download=Mock(status_code=200)
    download.__enter__=Mock(return_value=download)
    download.__exit__=Mock(return_value=False)
    download.iter_content.return_value=[base64.b64decode(MP4)]
    with patch.object(vp.requests,"post",return_value=response(302,headers={"Location":"https://results.s3.amazonaws.com/file"})), patch.object(vp.requests,"get",return_value=download) as get:
        vp.run_video(NVIDIA,vp.NVIDIA_VIDEO_MODEL,photo(),"room",1.5,"16:9")
    assert "headers" not in get.call_args.kwargs
    assert get.call_args.kwargs["allow_redirects"] is False

def test_private_result_url_rejected():
    with patch.object(vp.requests,"post",return_value=response(302,headers={"Location":"http://127.0.0.1/key"})), patch.object(vp.requests,"get") as get, pytest.raises(providers.ProviderRequestError):
        vp.run_video(NVIDIA,vp.NVIDIA_VIDEO_MODEL,photo(),"room",1.5,"16:9")
    get.assert_not_called()

def test_large_source_prepared_without_changing_source():
    source=photo()+b"padding"*(2*1024*1024)
    before=len(source)
    prepared=vp._input_image(source)
    assert len(prepared)<8*1024*1024
    assert len(source)==before
