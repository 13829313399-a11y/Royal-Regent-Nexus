/* Read only the images supplied by a user's native paste event. */
(function(root){
  'use strict';
  function images(event){
    const data=event.clipboardData;if(!data)return [];
    const items=[...(data.items||[])].filter(item=>item.kind==='file'&&item.type.startsWith('image/'));
    const files=items.length?items.map(item=>item.getAsFile()).filter(Boolean):[...(data.files||[])].filter(file=>file.type.startsWith('image/'));
    return files.map((file,i)=>file.name?file:new root.File([file],'粘贴图片-'+Date.now()+'-'+(i+1)+'.'+({ 'image/jpeg':'jpg','image/png':'png','image/webp':'webp' }[file.type]||'img'),{type:file.type}));
  }
  root.QcPhotoPaste={images};
})(window);
