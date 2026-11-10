import {describe,it,expect} from 'vitest';
import {createCanvas} from 'canvas';
import {resolve} from 'node:path';
import {registerDocumentFont} from '../../server/documentTypeset';
import {renderDocumentLayout,type DocumentRegion} from '../../server/documentLayout';
registerDocumentFont(resolve('server/dist'));

describe('generic complete-content document layout',()=>{
  it('renders unrelated adjacent columns separately and keeps a neighboring code unchanged',()=>{
    const source=createCanvas(600,180),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,600,180);
    c.fillStyle='black';c.font='22px Arial';c.fillText('Novel caption',20,58);c.fillText('Another column',220,58);c.fillText('00123',470,58);
    const regions:DocumentRegion[]=[
      {id:'a',sourceText:'Novel caption',translatedText:'新的图注',box:{x:18,y:35,width:150,height:28},translationStatus:'translated'},
      {id:'b',sourceText:'Another column',translatedText:'另一列说明',box:{x:218,y:35,width:180,height:28},translationStatus:'translated'},
      {id:'code',sourceText:'00123',translatedText:'00123',box:{x:468,y:35,width:90,height:28},skipReason:'protected'},
    ];
    const output=renderDocumentLayout(source,regions);
    expect(regions.slice(0,2).every(r=>r.rendered)).toBe(true);
    expect(output.getContext('2d').getImageData(460,20,140,70).data).toEqual(c.getImageData(460,20,140,70).data);
    // No drawing changes outside these text regions and their bounded padding.
    expect(output.getContext('2d').getImageData(0,100,600,80).data).toEqual(c.getImageData(0,100,600,80).data);
  });
  it('retains the complete translation when a paragraph cannot fit',()=>{
    const source=createCanvas(200,100),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,200,100);
    c.fillStyle='black';c.font='20px Arial';c.fillText('Label',20,50);
    const r:DocumentRegion={id:'x',sourceText:'Label',translatedText:'这是一段必须完整保留而不能因为原位空间不足就被丢弃的很长译文',box:{x:18,y:32,width:55,height:23},translationStatus:'translated'};
    const output=renderDocumentLayout(source,[r]);
    expect(r.rendered).toBe(false);expect(r.skipReason).toBe('layout-space');
    expect(r.translatedText).toContain('不能因为原位空间不足');
    expect(output.toBuffer()).toEqual(source.toBuffer());
  });
  it('does not paint an unverified translation onto the source',()=>{
    const source=createCanvas(200,100),c=source.getContext('2d');c.fillStyle='#e9eef3';c.fillRect(0,0,200,100);
    const r:DocumentRegion={id:'x',sourceText:'uncertain',translatedText:'未确认',box:{x:10,y:10,width:150,height:30},translationStatus:'needs_review',skipReason:'source-uncertain'};
    expect(renderDocumentLayout(source,[r]).toBuffer()).toEqual(source.toBuffer());
    expect(r.translatedText).toBe('未确认');expect(r.rendered).toBe(false);
  });
  it('does not let an unlocated page number block every physical caption',()=>{
    const source=createCanvas(300,100),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,300,100);
    c.fillStyle='black';c.font='20px Arial';c.fillText('Caption',25,50);
    const caption:DocumentRegion={id:'caption',sourceText:'Caption',translatedText:'图注',box:{x:23,y:30,width:90,height:24}};
    const number:DocumentRegion={id:'unknown',sourceText:'1',translatedText:'1',located:false,box:{x:0,y:0,width:300,height:100},skipReason:'protected'};
    renderDocumentLayout(source,[caption,number]);
    expect(caption.rendered).toBe(true);expect(number.rendered).toBe(false);
  });
  it('preserves a selected checkbox without requiring model metadata',()=>{
    const source=createCanvas(330,100),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,330,100);
    c.fillStyle='black';c.strokeStyle='black';c.lineWidth=1;c.strokeRect(20.5,35.5,15,15);
    c.beginPath();c.moveTo(23,43);c.lineTo(27,47);c.lineTo(32,38);c.stroke();
    c.font='20px Arial';c.fillText('Selected option',46,51);c.fillText('Caption',221,51);
    const selected:DocumentRegion={id:'selected',sourceText:'Selected option',translatedText:'已选择选项',box:{x:18,y:31,width:170,height:24}};
    const caption:DocumentRegion={id:'caption',sourceText:'Caption',translatedText:'图注',box:{x:220,y:31,width:88,height:24}};
    const rendered=renderDocumentLayout(source,[selected,caption]);
    expect(selected.skipReason).toBe('layout-form-control');expect(caption.rendered).toBe(true);
    expect(rendered.getContext('2d').getImageData(10,24,180,40).data).toEqual(c.getImageData(10,24,180,40).data);
  });
  it('never restores a previous English row while preserving a lower row padding',()=>{
    const source=createCanvas(350,150),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,350,150);
    c.fillStyle='black';c.font='24px Arial';c.fillText('Jacket',25,62);c.font='20px Arial';c.fillText('Soft material',25,88);
    const first:DocumentRegion={id:'a',sourceText:'Jacket',translatedText:'夹克',box:{x:23,y:40,width:100,height:25},fontSize:23};
    const lower:DocumentRegion={id:'b',sourceText:'Soft material',translatedText:'柔软面料',box:{x:23,y:65,width:160,height:25},fontSize:19};
    const alone=renderDocumentLayout(source,[{...first,box:{...first.box}},{...lower,skipReason:'protected'}]);
    const together=renderDocumentLayout(source,[first,lower]);
    expect(first.rendered&&lower.rendered).toBe(true);
    expect(together.getContext('2d').getImageData(25,56,96,7).data).toEqual(alone.getContext('2d').getImageData(25,56,96,7).data);
  });
});
