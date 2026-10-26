interface Viewport { width: number; height: number; left: number; top: number }
interface Target { left: number; top: number; right: number; bottom: number }

/** Keep the guide inside the viewport, clear of higher native layers and its target. */
export function placeGuide(viewport: Viewport, measuredHeight: number, target: Target | null, obstacles: Target[] = []) {
  const margin = viewport.width < 768 ? 14 : 24
  const width = Math.max(0, Math.min(380, viewport.width - margin * 2))
  const maxHeight = Math.max(0, viewport.height - margin * 2)
  const height = Math.min(measuredHeight || 185, maxHeight)
  const left = viewport.left + margin, right = viewport.left + viewport.width - margin - width
  const top = viewport.top + margin, bottom = viewport.top + viewport.height - margin - height
  const candidates = [{x:left,y:bottom}, {x:left,y:top}, {x:right,y:bottom}, {x:right,y:top}]
  const overlap = ({x,y}: {x:number;y:number}, rect:Target, gap=0) =>
    Math.max(0, Math.min(x+width,rect.right+gap)-Math.max(x,rect.left-gap))
      * Math.max(0, Math.min(y+height,rect.bottom+gap)-Math.max(y,rect.top-gap))
  const blocked = (point:{x:number;y:number}) => obstacles.reduce((area,rect)=>area+overlap(point,rect,8),0)
  const coveredTarget = (point:{x:number;y:number}) => target ? overlap(point,target,8) : 0
  const chosen = candidates.reduce((best, candidate) => {
    const difference=blocked(candidate)-blocked(best)
    return difference<0 || (difference===0 && coveredTarget(candidate)<coveredTarget(best)) ? candidate : best
  })
  return {...chosen,width,maxHeight}
}
