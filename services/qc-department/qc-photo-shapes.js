(function(root){
  'use strict';
  const coordinates=['x1','y1','x2','y2'];
  const toolButtons=`
    <button type="button" data-mark-tool="browse" aria-pressed="true"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 3 14 10-7 1-3 6z"/></svg>浏览</button>
    <button type="button" data-mark-tool="arrow" aria-pressed="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19 19 5M10 5h9v9"/></svg>箭头</button>
    <button type="button" data-mark-tool="circle" aria-pressed="false"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7"/></svg>圆圈</button>
    <button type="button" data-mark-undo aria-label="撤销" title="撤销"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5-5 5 5 5M4 10h10a5 5 0 0 1 0 10h-2"/></svg></button>
    <button type="button" data-mark-redo aria-label="重做" title="重做"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5 5 5-5 5m5-5H10a5 5 0 0 0 0 10h2"/></svg></button>`;
  function equal(first=[],second=[]){
    return first.length===second.length&&first.every((mark,index)=>
      mark.type===second[index].type&&coordinates.every(key=>mark[key]===second[index][key]));
  }
  function paint(layer,width,height,marks){
    const stroke=Math.max(2,Math.min(width,height)*.006);
    layer.replaceChildren(...marks.map(mark=>{
      const x1=mark.x1*width,y1=mark.y1*height,x2=mark.x2*width,y2=mark.y2*height;
      const circle=mark.type==='circle';
      const node=layer.ownerDocument.createElementNS('http://www.w3.org/2000/svg',circle?'ellipse':'path');
      if(circle){
        node.setAttribute('cx',(x1+x2)/2);node.setAttribute('cy',(y1+y2)/2);
        node.setAttribute('rx',Math.abs(x2-x1)/2);node.setAttribute('ry',Math.abs(y2-y1)/2);
      }else{
        const angle=Math.atan2(y2-y1,x2-x1);
        const head=Math.min(stroke*5.5,Math.hypot(x2-x1,y2-y1)*.5);
        const wing=offset=>`${x2-head*Math.cos(angle+offset)} ${y2-head*Math.sin(angle+offset)}`;
        node.setAttribute('d',`M${x1} ${y1}L${x2} ${y2}M${wing(.65)}L${x2} ${y2}L${wing(-.65)}`);
      }
      node.setAttribute('stroke-width',stroke);
      return node;
    }));
  }
  root.QcPhotoShapes={equal,paint,toolButtons};
})(window);
