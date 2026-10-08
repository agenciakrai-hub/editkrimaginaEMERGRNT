// Global projective mapping for the new manual editor only.
export function projectPerspective(source, horizontal, vertical) {
  if (!horizontal && !vertical) return source;
  const { width:w, height:h } = source;
  const out=document.createElement("canvas"); out.width=w; out.height=h;
  const ctx=out.getContext("2d"), input=source.getContext("2d").getImageData(0,0,w,h).data;
  const result=ctx.createImageData(w,h), d=result.data, px=horizontal/70, py=vertical/70;
  for(let y=0;y<h;y++) for(let x=0;x<w;x++) {
    const u=(x+0.5)/w-0.5,v=(y+0.5)/h-0.5,den=1-px*u-py*v;
    if(den<=0) continue;
    const sx=(u/den+0.5)*w-0.5,sy=(v/den+0.5)*h-0.5;
    if(sx<0||sy<0||sx>w-1||sy>h-1) continue;
    const ix=Math.floor(sx),iy=Math.floor(sy),fx=sx-ix,fy=sy-iy;
    const a=(iy*w+ix)*4,b=(iy*w+Math.min(ix+1,w-1))*4,c=(Math.min(iy+1,h-1)*w+ix)*4,e=(Math.min(iy+1,h-1)*w+Math.min(ix+1,w-1))*4,o=(y*w+x)*4;
    for(let k=0;k<4;k++) d[o+k]=(1-fy)*((1-fx)*input[a+k]+fx*input[b+k])+fy*((1-fx)*input[c+k]+fx*input[e+k]);
  }
  ctx.putImageData(result,0,0); return out;
}
