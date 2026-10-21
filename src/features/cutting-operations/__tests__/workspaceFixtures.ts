// Existing editor regressions isolate the added read-only overview requests.
// Projection behavior is exercised separately in workspace.spec.ts/backend tests.
const page={data:[],total:0,page:1,page_size:50}
export const businessDay=()=>'2026-10-20'
export const workspaceApi={
  planning:async()=>({...page,stats:{total:0,scheduled:0,unscheduled:0,partial:0,review:0}}),
  tasks:async()=>({...page,day:'2026-10-20',stats:{tasks:0,reported:0,unreported:0,planned:0,completed:0,handed:0,abnormal:0,unplanned_facts:0}}),
  inventory:async()=>({...page,units:{}}),
  costs:async()=>({...page,currencies:{},pending_pricing:0}),
  activity:async()=>page,
  masters:async()=>({bom:0,draft:0,material:0,resource:0}),
  monthly:async()=>({month:'2026-10',domains:[],frozen:[]}),
}
