(function(){
  'use strict';
  var dialog=document.getElementById('lfv-archive-modal');
  if(!dialog)return;
  var windowEl=dialog.querySelector('.lfv-archive-modal__window');
  var form=dialog.querySelector('[data-archive-form]');
  var status=dialog.querySelector('[data-archive-status]');
  var submit=form.querySelector('[type=submit]');
  var lastFocus=null;
  function open(event){
    if(event)event.preventDefault();
    lastFocus=document.activeElement;
    dialog.hidden=false;
    document.body.style.overflow='hidden';
    windowEl.focus();
  }
  function close(){
    dialog.hidden=true;
    document.body.style.overflow='';
    if(lastFocus&&lastFocus.focus)lastFocus.focus();
  }
  document.querySelectorAll('[data-open-archive-contribution]').forEach(function(button){
    button.addEventListener('click',open);
  });
  dialog.querySelectorAll('[data-archive-close]').forEach(function(button){
    button.addEventListener('click',close);
  });
  document.addEventListener('keydown',function(event){
    if(dialog.hidden)return;
    if(event.key==='Escape'){event.preventDefault();close();return;}
    if(event.key!=='Tab')return;
    var focusable=Array.prototype.slice.call(dialog.querySelectorAll('button:not(:disabled),input:not([type=hidden]):not([tabindex="-1"]),select,textarea,a[href]'))
      .filter(function(node){return node.offsetParent!==null;});
    if(!focusable.length)return;
    var first=focusable[0],last=focusable[focusable.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  });
  form.addEventListener('submit',function(event){
    if(!window.fetch)return;
    event.preventDefault();
    var fields=new FormData(form);
    if(!fields.get('source_url')&&!String(fields.get('source_description')||'').trim()){
      status.textContent='Include a source link or explain how the information is known.';
      return;
    }
    status.textContent='Submitting for review…';
    submit.disabled=true;
    fetch(form.action,{method:'POST',body:fields,credentials:'same-origin',headers:{'Accept':'application/json'}})
      .then(function(response){return response.json().then(function(data){return {ok:response.ok,data:data};});})
      .then(function(result){
        status.textContent=result.data.message||result.data.error||(result.ok?'Received.':'Could not submit.');
        if(result.ok){form.reset();status.setAttribute('data-success','true');submit.textContent='Submitted';}
      })
      .catch(function(){status.textContent='Unable to submit. Please retry, or use the full submission page.';})
      .finally(function(){submit.disabled=false;});
  });
  if(new URLSearchParams(window.location.search).get('archive_submitted')==='1'){
    var section=document.getElementById('contribute');
    if(section){var message=document.createElement('p');message.setAttribute('role','status');message.textContent='Historical information received for private archive review.';section.appendChild(message);}
  }
})();
