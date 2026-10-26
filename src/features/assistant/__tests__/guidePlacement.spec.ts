import { describe, expect, it } from 'vitest'
import { placeGuide } from '../guidePlacement'

const desktop = {width:1440,height:900,left:0,top:0}
function intersects(p:ReturnType<typeof placeGuide>,height:number,t:{left:number;top:number;right:number;bottom:number}) {
  return p.x<t.right && p.x+p.width>t.left && p.y<t.bottom && p.y+height>t.top
}
describe('guide placement around native page targets', () => {
  it('leaves the 3D lower-left synchronization controls visible', () => {
    const target={left:12,top:733,right:203,bottom:768}
    const p=placeGuide(desktop,185,target)
    expect(intersects(p,185,target)).toBe(false)
    expect(p.y).toBeLessThan(target.top)
  })
  it('keeps both navigation and a tall guide accessible without covering the target', () => {
    const target={left:0,top:95,right:215,bottom:589}
    const p=placeGuide(desktop,420,target)
    expect(intersects(p,420,target)).toBe(false)
    expect(p.y+420).toBeLessThanOrEqual(900)
  })
  it('fits a narrow keyboard viewport with offsets and scrolls long instructions', () => {
    const v={width:375,height:320,left:6,top:200}
    const p=placeGuide(v,900,{left:20,top:300,right:350,bottom:340})
    expect(p.x).toBeGreaterThanOrEqual(v.left)
    expect(p.x+p.width).toBeLessThanOrEqual(v.left+v.width)
    expect(p.y).toBeGreaterThanOrEqual(v.top)
    expect(p.y+p.maxHeight).toBeLessThanOrEqual(v.top+v.height)
  })
  it('retains the unobstructed default position instead of moving needlessly', () => {
    const p=placeGuide(desktop,185,{left:550,top:260,right:678,bottom:300})
    expect(p.x).toBe(24)
    expect(p.y).toBe(691)
  })
  it('keeps guide controls outside the customer-order fixed navigation and header', () => {
    const sidebar={left:0,top:64,right:240,bottom:900}
    const header={left:0,top:0,right:1440,bottom:64}
    const target={left:264,top:182,right:1400,bottom:220}
    const p=placeGuide(desktop,185,target,[sidebar,header])
    expect(intersects(p,185,sidebar)).toBe(false)
    expect(intersects(p,185,header)).toBe(false)
    expect(intersects(p,185,target)).toBe(false)
  })
  it('prioritizes reachable controls when a full-width target leaves no completely clear corner', () => {
    const sidebar={left:0,top:0,right:240,bottom:900}
    const target={left:240,top:0,right:1440,bottom:900}
    const p=placeGuide(desktop,185,target,[sidebar])
    expect(intersects(p,185,sidebar)).toBe(false)
  })
})
