(function(){
  'use strict';
  var dialog=document.getElementById('lfv-archive-modal');
  var lastFocus=null;
  function open(event){
    if(!dialog)return;
    if(event)event.preventDefault();
    lastFocus=document.activeElement;
    dialog.hidden=false;
    document.body.style.overflow='hidden';
    dialog.querySelector('.lfv-archive-modal__window').focus();
  }
  function close(){
    if(!dialog)return;
    dialog.hidden=true;
    document.body.style.overflow='';
    if(lastFocus&&lastFocus.focus)lastFocus.focus();
  }
  document.querySelectorAll('[data-open-archive-contribution]').forEach(function(button){
    button.addEventListener('click',open);
  });
  if(dialog){
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
  }

  // Works in the popup, on the standalone page, and on the general /submit page.
  document.querySelectorAll('[data-archive-form]').forEach(function(form){
    var type=form.querySelector('[data-archive-type-select]');
    var groups=Array.prototype.slice.call(form.querySelectorAll('[data-archive-type]'));
    var hint=form.querySelector('[data-archive-type-hint]');
    var status=form.querySelector('[data-archive-status]');
    var submit=form.querySelector('[type=submit]');
    function syncType(){
      var current=type.value;
      groups.forEach(function(group){
        var active=group.getAttribute('data-archive-type')===current;
        group.hidden=!active;group.disabled=!active;
        // Do not submit a different type's filled-in answers.
        group.querySelectorAll('input,select,textarea').forEach(function(input){
          input.disabled=!active;
        });
      });
      if(hint)hint.textContent=current?'Complete the questions for your selected submission type below.':'Select a type to see the relevant questions.';
    }
    type.addEventListener('change',syncType);
    syncType();
    form.addEventListener('submit',function(event){
      if(!window.fetch)return; // HTML form POST works as a fallback.
      event.preventDefault();
      var fields=new FormData(form);
      if(!fields.get('source_url')&&!String(fields.get('source_description')||'').trim()){
        status.textContent='Include a source link or explain how the information is known.';
        return;
      }
      status.textContent='Submitting for review…';
      submit.disabled=true;
      fetch(form.action,{method:'POST',body:fields,credentials:'same-origin',headers:{Accept:'application/json'}})
        .then(function(response){return response.json().then(function(data){return {ok:response.ok,data:data};});})
        .then(function(result){
          status.textContent=result.data.message||result.data.error||(result.ok?'Received.':'Could not submit.');
          if(result.ok){
            form.reset();syncType();
            status.setAttribute('data-success','true');
            submit.textContent='Submitted';
            // Keep the confirmation in place, preventing duplicate resubmission.
            submit.disabled=true;
          }else{submit.disabled=false;}
        })
        .catch(function(){
          status.textContent='Unable to submit. Please retry, or use the full submission page.';
          submit.disabled=false;
        });
    });
  });
  if(new URLSearchParams(window.location.search).get('archive_submitted')==='1'){
    var section=document.getElementById('contribute');
    if(section){
      var message=document.createElement('p');
      message.setAttribute('role','status');
      message.textContent='Historical information received for private archive review.';
      section.appendChild(message);
    }
  }
})();