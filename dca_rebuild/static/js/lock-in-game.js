/* Lock In demo battle table. Unspecified scoring stays manual, not invented. */
(function () {
  "use strict";
  var root=document.getElementById("lock-workbench");
  if(!root)return;
  var samples=JSON.parse(document.getElementById("lock-samples").textContent);
  var types=["Dancer","Arena","Song","Move","Trick","Upgrade","Frib"];
  var restrictions=JSON.parse(document.getElementById("lock-restrictions").textContent || "{}");
  var storeKey="litefeet-lockin-draft-deck-v1";
  function limit(id){return Object.prototype.hasOwnProperty.call(restrictions,id)?restrictions[id]:3;}
  var all=samples.map(function(s){return s.categories.reduce(function(a,g){return a.concat(g.type==="Producer"?[]:g.cards.map(function(n){return {id:g.type+"::"+n,type:g.type,name:n};}));},[]);});
  var pool={}; all.forEach(function(a){a.forEach(function(c){pool[c.id]=c;});});
  JSON.parse(document.getElementById("lock-card-catalog").textContent).forEach(function(card){if(card.type!=="Producer")pool[card.id]=card;});
  var deck=all[0].slice(),round=1,hand=[],selected=[],history=[],chosen={};
  function setGameMode(mode){
    var battle=mode==="battle", moves=mode==="moves";
    el("#lock-battle-mode").hidden=!battle;
    el("#lock-moves-mode").hidden=!moves;
    root.querySelectorAll('input[name="lock-game-mode"]').forEach(function(input){
      input.checked=input.value===mode;
    });
  }
  function el(s){return root.querySelector(s);}
  function escape(s){return String(s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
  function amount(id){return deck.filter(function(c){return c.id===id;}).length;}
  function limits(){return deck.every(function(c){return Number.isInteger(limit(c.id))&&limit(c.id)>=0&&limit(c.id)<=3&&amount(c.id)<=limit(c.id);});}
  function problems(){
    var p=[];
    if(deck.length<25||deck.length>50)p.push("A deck must contain 25–50 total cards.");
    if(!limits())p.push("Card count exceeds its restriction: Unlimited 3, Semi-Limited 2, Limited 1, Forbidden 0.");
    ["Dancer","Song","Arena"].forEach(function(t){if(!deck.some(function(c){return c.type===t;}))p.push("A "+t+" card is required for this 1v1 setup.");});
    return p;
  }
  function options(t){
    var seen={};
    return deck.filter(function(c){if(c.type!==t||seen[c.id])return false;seen[c.id]=true;return true;}).sort(function(a,b){return a.name.localeCompare(b.name,undefined,{sensitivity:"base",numeric:true});}).map(function(c){var detail=t==="Song"&&pool[c.id]&&pool[c.id].producer?" · Prod. "+pool[c.id].producer:"";return '<option value="'+escape(c.id)+'">'+escape(c.name+detail)+'</option>';}).join("");
  }
  function renderDeck(){
    el("#lock-count").textContent=deck.length;
    el("#lock-categories").textContent=types.filter(function(t){return deck.some(function(c){return c.type===t;});}).map(function(t){return t+": "+deck.filter(function(c){return c.type===t;}).length;}).join(" · ");
    var counts={};deck.forEach(function(c){counts[c.id]=(counts[c.id]||0)+1;});
    el("#lock-deck-list").innerHTML=Object.keys(counts).map(function(id){
      var c=pool[id];return '<li><span>'+escape(c.type)+' · '+escape(c.name)+' ×'+counts[id]+'</span> <button data-remove="'+escape(id)+'" type="button" aria-label="Remove '+escape(c.name)+'">−</button><button data-add="'+escape(id)+'" type="button" '+(counts[id]>=limit(id)?"disabled":"")+' aria-label="Add '+escape(c.name)+'">+</button></li>';
    }).join("");
    var p=problems();el("#lock-validation").textContent=p.length?p.join(" "):"Deck meets the size and general three-copy limits.";
    el("#lock-start").disabled=!!p.length;
  }
  function renderCatalog(){
    var type=el("#lock-filter").value;
    var query=(el("#lock-search").value||"").trim().toLocaleLowerCase();
    var parts=query.split(/\s+/).filter(Boolean);
    var candidates=Object.keys(pool).filter(function(id){
      if(type!=="all"&&pool[id].type!==type)return false;
      var searchable=(pool[id].type+" "+pool[id].name+" "+(pool[id].producer||"")+" "+(pool[id].artist||"")).toLocaleLowerCase();
      return parts.every(function(word){return searchable.includes(word);});
    }).sort(function(a,b){
      var aa=pool[a].name.toLocaleLowerCase(),bb=pool[b].name.toLocaleLowerCase();
      var astart=aa.startsWith(query)?0:1,bstart=bb.startsWith(query)?0:1;
      return astart-bstart||aa.localeCompare(bb,undefined,{sensitivity:"base",numeric:true});
    }).slice(0,30);
    el("#lock-catalog").innerHTML=candidates.map(function(id){
      return '<option value="'+escape(id)+'">'+escape(pool[id].type+" · "+pool[id].name+(pool[id].producer?" · Prod. "+pool[id].producer:""))+'</option>';
    }).join("");
    el("#lock-search-feedback").textContent=candidates.length?candidates.length+" matching cards":"No matching cards. You can request a new one.";
    el("#lock-add").disabled=candidates.length===0;
  }


  // Practice phases: Rev Up -> footwork/combo/trick -> optional Frib -> Lock In.
  // Preserve names and don't infer undocumented move classifications.
  var practiceScenario=null;
  function practiceCandidates(type){
    return Object.keys(pool).map(function(id){return pool[id];})
      .filter(function(card){return card.type===type;})
      .sort(function(a,b){return a.name.localeCompare(b.name,undefined,{sensitivity:"base"});});
  }
  function randomOne(cards){return cards[Math.floor(Math.random()*cards.length)];}
  function chooseResponse(id,phase){
    if(!practiceScenario||!pool[id])return;
    var card=pool[id];
    if(phase==="rev"&&card.type==="Move"&&card.move_family==="Rev Ups"){
      practiceScenario.rev=id;
    }
    if(phase==="main"&&(card.type==="Move"||card.type==="Trick")){
      practiceScenario.main=id;
      if(id===practiceScenario.trick)practiceScenario.trick="";
    }
    if(phase==="frib"&&card.type==="Frib"){
      practiceScenario.trick=practiceScenario.trick===id?"":id;
    }
    renderPracticeSelection();
  }
  function renderPracticeSelection(){
    if(!practiceScenario)return;
    var sc=practiceScenario;
    var ready=!!sc.rev&&!!sc.main;
    var stage=!sc.rev?"rev":!sc.main?"main":"frib";
    el("#lock-response-count").textContent=!sc.rev?
      "1. Choose your Rev Up":!sc.main?
      "2. Choose Footwork, Combo, or Trick":
      "3. Add a Frib Card (optional), then Lock In";
    function describe(id, fallback){return id?escape(pool[id].name):fallback;}
    el("#lock-selected-moves").innerHTML=
      '<div class="lock-sequence-card"><span>1. Rev Up · '+describe(sc.rev,"Choose a Rev Up")+'</span></div>'+
      '<div class="lock-sequence-card"><span>2. Footwork / Combo / Trick · '+describe(sc.main,"Choose your main move")+'</span></div>'+
      '<div class="lock-sequence-card"><span>3. Optional Frib Card · '+describe(sc.trick,"None")+'</span></div>'+
      '<div class="lock-sequence-card"><span>4. Lock In</span></div>';
    var eligible;
    if(stage==="rev") eligible=practiceCandidates("Move").filter(function(card){return card.move_family==="Rev Ups";});
    else if(stage==="main") eligible=sc.moves;
    else eligible=sc.fribs.filter(function(card){return card.id!==sc.main;});
    if(stage==="main") {
      // Stutter Step is documented footwork. Unclassified individual moves
      // are not mislabeled as confirmed combo or footwork variants.
      el("#lock-response-moves").innerHTML=eligible.map(function(card){
        var type=card.type==="Trick"?"Trick":(card.move_family||"Move");
        return '<button type="button" class="lock-game-card lock-available-card" data-practice-phase="main" data-card-id="'+escape(card.id)+'">'+
          '<span class="lock-card-category">'+escape(type)+'</span><strong>'+escape(card.name)+'</strong>'+
          '<span class="lock-card-hint">Use as main move</span></button>';
      }).join("");
    } else {
      el("#lock-response-moves").innerHTML=eligible.map(function(card){
        return '<button type="button" class="lock-game-card lock-available-card" data-practice-phase="'+stage+'" data-card-id="'+escape(card.id)+'" '+
          (stage==="frib"&&sc.trick===card.id?'aria-pressed="true"':'aria-pressed="false"')+'>'+
          '<span class="lock-card-category">'+(stage==="rev"?"REV UP":"FRIB CARD")+'</span>'+
          '<strong>'+escape(card.name)+'</strong><span class="lock-card-hint">'+
          (stage==="frib"&&sc.trick===card.id?"Selected · tap to remove":"Select card")+'</span></button>';
      }).join("");
      if(stage==="frib"){
        el("#lock-response-moves").innerHTML='<button type="button" class="lock-skip-trick" id="lock-no-trick">No Frib Card</button>'+
          '<button type="button" class="lock-practice-edit" id="lock-change-main">Change main move</button>'+
          '<button type="button" class="lock-practice-edit" id="lock-change-rev">Change Rev Up</button>'+
          el("#lock-response-moves").innerHTML;
      }
    }
    el("#lock-score-response").disabled=!ready;
    el("#lock-response-result").hidden=true;
  }
  function generateSituation(){
    var moves=practiceCandidates("Move"),songs=practiceCandidates("Song"),
      arenas=practiceCandidates("Arena"),tricks=practiceCandidates("Trick"),fribs=practiceCandidates("Frib");
    var revs=moves.filter(function(card){return card.move_family==="Rev Ups";});
    if(!revs.length||moves.length<2||!songs.length||!arenas.length){
      el("#lock-generated-situation").hidden=false;
      el("#lock-response-moves").textContent="There aren't enough cards to create a practice round.";
      el("#lock-score-response").disabled=true;
      return;
    }
    var opponent=randomOne(moves);
    var mainMoves=shuffle(moves.filter(function(card){return card.id!==opponent.id&&card.move_family!=="Rev Ups";}));
    // Include documented footwork and a mix of other moves and tricks.
    var footwork=mainMoves.find(function(card){return card.move_family==="Footwork";});
    var responses=footwork?[footwork]:[];
    mainMoves.forEach(function(card){
      if(responses.length<6&&!responses.some(function(item){return item.id===card.id;}))responses.push(card);
    });
    shuffle(tricks).slice(0,2).forEach(function(card){responses.push(card);});
    practiceScenario={opponent:opponent,song:randomOne(songs),arena:randomOne(arenas),
      moves:shuffle(responses),fribs:fribs,rev:"",main:"",trick:""};
    el("#lock-first-situation").hidden=true;
    el("#lock-generated-situation").hidden=false;
    el("#lock-opponent-move").textContent=practiceScenario.opponent.name;
    el("#lock-opponent-song").textContent=practiceScenario.song.name+
      (practiceScenario.song.producer?" · Prod. "+practiceScenario.song.producer:"");
    el("#lock-opponent-arena").textContent=practiceScenario.arena.name;
    renderPracticeSelection();
  }
  function scoreSituation(){
    if(!practiceScenario||!practiceScenario.rev||!practiceScenario.main)return;
    var sc=practiceScenario;
    var sequence=[sc.rev,sc.main].concat(sc.trick?[sc.trick]:[]).map(function(id){return pool[id].name;});
    var result=el("#lock-response-result");
    result.hidden=false;
    result.innerHTML='<h5>Locked in</h5>'+
      '<p><strong>Your move set:</strong> '+sequence.map(escape).join(' → ')+' → Lock In</p>'+
      '<p><strong>Opponent:</strong> '+escape(sc.opponent.name)+' to '+
      escape(sc.song.name)+' at '+escape(sc.arena.name)+'.</p>'+
      '<p>Move set complete. Battle Points, counter effects and the winner will be determined by the finalized card rules.</p>';
  }
  function shuffle(cards){var a=cards.slice();for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),x=a[i];a[i]=a[j];a[j]=x;}return a;}
  function cardName(id){return pool[id]?pool[id].name:"";}
  function drawBattle(){
    var table=el("#lock-battle");table.hidden=false;
    table.innerHTML='<h3>Round '+round+' · Arena and card setup</h3><p>Shuffle and cut the decks, then spin the adidas counter. Record the first turn below; a physical spin is not simulated.</p>'+
      '<label>Dancer <select id="lock-dancer">'+options("Dancer")+'</select></label>'+
      '<label>Song <select id="lock-song">'+options("Song")+'</select></label>'+
      '<label>Arena <select id="lock-arena">'+options("Arena")+'</select></label>'+
      
      '<label>Who goes first? <select id="lock-order"><option>You</option><option>Opponent</option></select></label>'+
      '<button id="lock-draw" type="button">Set cards and draw hand</button>';
  }
  function renderHand(){
    var table=el("#lock-battle");
    table.innerHTML='<h3>Round '+round+' · Move set</h3><p>'+escape(chosen.dancer+' · '+chosen.song+' · '+chosen.arena)+'</p>'+
      '<p>Hand cards: '+hand.length+'. Choose up to three move cards. Special effects not assigned BP in the rulebook must be adjudicated manually.</p>'+
      '<div class="lock-hand">'+hand.map(function(c,i){return '<label><input type="checkbox" data-pick="'+i+'"> '+escape(c.type+" · "+c.name)+'</label>';}).join("")+'</div>'+
      '<p id="lock-selection" aria-live="polite">0 / 3 moves selected</p><button type="button" id="lock-announce">Announce locked in</button>';
  }
  function renderScoring(){
    el("#lock-battle").innerHTML='<h3>Round '+round+' · Resolve</h3>'+
      '<p>Moves and effects played: '+escape(selected.map(function(i){return hand[i].name;}).join(" · ")||"none")+'</p>'+
      '<p>Enter adjudicated points from your card rules. The full card BP table is not final; this prototype does not award arbitrary bonuses.</p>'+
      '<label>Your BP <input type="number" id="lock-my-bp" value="100"></label>'+
      '<label>Opponent BP <input type="number" id="lock-their-bp" value="100"></label>'+
      '<label><input type="checkbox" id="lock-missed"> Missed Lock In called out (−10 BP)</label>'+
      '<label><input type="checkbox" id="lock-challenge"> Incorrect card-validity challenge (−50 BP)</label>'+
      '<label><input type="checkbox" id="lock-draw-loss"> Opponent cannot draw</label>'+
      '<label><input type="checkbox" id="lock-tko"> Officially adjudicated TKO</label>'+
      '<button type="button" id="lock-resolve">Resolve round</button>';
  }
  root.addEventListener("change",function(e){
    if(e.target.name==="lock-game-mode"){
      setGameMode(e.target.value);
      return;
    }
    if(e.target.id==="lock-sample"){deck=all[Number(e.target.value)].slice();el("#lock-battle").hidden=true;renderDeck();}
    if(e.target.id==="lock-filter")renderCatalog();
    if(e.target.id==="lock-request-type"){
      var kind=e.target.value;
      root.querySelectorAll(".lock-request-fields").forEach(function(group){group.hidden=group.dataset.requestType!==kind;});
    }
    if(e.target.hasAttribute("data-pick")){
      var i=Number(e.target.getAttribute("data-pick")),isMove=hand[i].type==="Move";
      if(e.target.checked){if(isMove&&selected.filter(function(j){return hand[j].type==="Move";}).length>=3){e.target.checked=false;return;}selected.push(i);}
      else selected=selected.filter(function(j){return j!==i;});
      el("#lock-selection").textContent=selected.filter(function(j){return hand[j].type==="Move";}).length+" / 3 moves selected";
    }
  });
  root.addEventListener("click",function(e){
    var b=e.target.closest("button");if(!b)return;
    if(b.id==="lock-suggest-move"){
      var panel=el("#lock-request-panel");
      panel.hidden=false;
      el("#lock-request-open").setAttribute("aria-expanded","true");
      el("#lock-request-type").value="Move";
      el("#lock-request-type").dispatchEvent(new Event("change",{bubbles:true}));
      panel.scrollIntoView({block:"start",behavior:"smooth"});
      el("#lock-request-name").focus();
      return;
    }
    if(b.id==="lock-first-situation"||b.id==="lock-generate-situation"){generateSituation();return;}
    if(b.id==="lock-score-response"){scoreSituation();return;}
    if(b.hasAttribute("data-card-id")&&b.hasAttribute("data-practice-phase")){
      chooseResponse(b.getAttribute("data-card-id"),b.getAttribute("data-practice-phase"));return;
    }
    if(b.id==="lock-no-trick"&&practiceScenario){
      practiceScenario.trick="";renderPracticeSelection();return;
    }
    if(b.id==="lock-change-main"&&practiceScenario){
      practiceScenario.main="";practiceScenario.trick="";renderPracticeSelection();return;
    }
    if(b.id==="lock-change-rev"&&practiceScenario){
      practiceScenario.rev="";practiceScenario.main="";practiceScenario.trick="";renderPracticeSelection();return;
    }
    if(b.hasAttribute("data-remove")){var id=b.getAttribute("data-remove"),i=deck.findIndex(function(c){return c.id===id;});if(i>=0)deck.splice(i,1);renderDeck();return;}
    if(b.hasAttribute("data-add")){var id=b.getAttribute("data-add");if(amount(id)<limit(id))deck.push(pool[id]);renderDeck();return;}
    if(b.id==="lock-add"){
      var id=el("#lock-catalog").value;
      if(id&&pool[id]&&amount(id)<limit(id)){deck.push(pool[id]);renderDeck();}
    }
    if(b.hasAttribute("data-deck-sample")){
      var index=Number(b.getAttribute("data-deck-sample"));
      if(all[index]){deck=all[index].slice();el("#lock-sample").value=String(index);renderDeck();document.getElementById("lock-workbench").scrollIntoView({block:"start",behavior:"smooth"});}
      return;
    }
    if(b.id==="lock-request-open"){
      var panel=el("#lock-request-panel");
      panel.hidden=!panel.hidden;
      b.setAttribute("aria-expanded",String(!panel.hidden));
      if(!panel.hidden){
        el("#lock-request-name").value=el("#lock-search").value.trim();
        var requestTypes=["Dancer","Song","Arena","Move","Trick","Upgrade","Frib"];
        el("#lock-request-type").value=requestTypes.includes(el("#lock-filter").value)?el("#lock-filter").value:"Dancer";
        el("#lock-request-type").dispatchEvent(new Event("change",{bubbles:true}));
        el("#lock-request-name").focus();
      }
      return;
    }
    if(b.id==="lock-save"){
      var issues=problems();
      if(issues.length){el("#lock-save-status").textContent="Cannot save: "+issues.join(" ");return;}
      try{window.localStorage.setItem(storeKey,JSON.stringify(deck.map(function(card){return card.id;})));el("#lock-save-status").textContent="Saved to this browser only; no account or server storage."; }
      catch(err){el("#lock-save-status").textContent="Local storage is unavailable in this browser.";}
      return;
    }
    if(b.id==="lock-load"){
      try{
        var saved=JSON.parse(window.localStorage.getItem(storeKey)||"null");
        if(!Array.isArray(saved)||saved.some(function(id){return !pool[id];})){el("#lock-save-status").textContent="No compatible saved deck found.";return;}
        var previous=deck;deck=saved.map(function(id){return pool[id];});
        var issues=problems();
        if(issues.length){deck=previous;el("#lock-save-status").textContent="Saved deck is no longer valid: "+issues.join(" ");return;}
        renderDeck();el("#lock-save-status").textContent="Loaded locally saved deck.";
      }catch(err){el("#lock-save-status").textContent="Could not load saved deck.";}
      return;
    }
    if(b.id==="lock-start"){if(!problems().length){round=1;history=[];drawBattle();}}
    if(b.id==="lock-draw"){
      var played=[el("#lock-dancer").value,el("#lock-song").value,el("#lock-arena").value];
      chosen={dancer:cardName(played[0]),song:cardName(played[1]),arena:cardName(played[2]),first:el("#lock-order").value};
      var eligible=deck.filter(function(c){return ["Move","Trick","Upgrade","Frib"].indexOf(c.type)>=0&&played.indexOf(c.id)<0;});
      hand=shuffle(eligible).slice(0,7);selected=[];renderHand();
    }
    if(b.id==="lock-announce")renderScoring();
    if(b.id==="lock-resolve"){
      var mine=el("#lock-my-bp"),other=el("#lock-their-bp");
      if(mine.value===""||other.value==="")return;
      var p=Number(mine.value),q=Number(other.value);
      if(!Number.isFinite(p)||!Number.isFinite(q))return;
      p-=el("#lock-missed").checked?10:0;
      p-=el("#lock-challenge").checked?50:0;
      var outcome=p<50&&q<50?"Both below 50 BP — manual adjudication needed":p<50?"Automatic loss — your BP below 50":q<50?"Opponent automatic loss":el("#lock-draw-loss").checked||el("#lock-tko").checked?"Win by adjudicated special condition":p>q?"You win":p<q?"Opponent wins":"Tie — Round of Fire draft";
      history.push("Round "+round+": "+p+" to "+q+" BP · "+outcome);
      el("#lock-battle").innerHTML='<h3>Round result</h3><p>'+escape(outcome)+'</p><p>'+history.map(escape).join("<br>")+'</p><p>Battle victory thresholds are still blank in the rulebook; this does not claim an official battle winner.</p>'+(round<2?'<button type="button" id="lock-next">Next round</button>':'<p>Two-round 1v1 practice complete. Tied rounds and unfinished battle thresholds require the final rulebook.</p><button type="button" id="lock-restart">Start a new battle</button>');
    }
    if(b.id==="lock-next"){round++;drawBattle();}
    if(b.id==="lock-restart"){round=1;history=[];drawBattle();}
  });
  el("#lock-sample").innerHTML=samples.map(function(s,i){return '<option value="'+i+'">'+escape(s.name)+'</option>';}).join("");
  el("#lock-filter").innerHTML='<option value="all">All types</option>'+types.map(function(t){return '<option value="'+t+'">'+t+'</option>';}).join("");
  el("#lock-search").addEventListener("input",renderCatalog);
  el("#lock-search").addEventListener("keydown",function(e){
    if(e.key==="Enter"){e.preventDefault();el("#lock-add").click();}
  });
  el("#lock-request-form").addEventListener("submit",function(e){
    e.preventDefault();
    var form=e.currentTarget;
    var feedback=el("#lock-request-feedback");
    var button=form.querySelector('[type="submit"]');
    button.disabled=true;
    feedback.textContent="Sending…";
    fetch(form.action,{method:"POST",body:new FormData(form),credentials:"same-origin",headers:{"Accept":"application/json"}})
      .then(function(response){return response.json().then(function(json){return {ok:response.ok,data:json};});})
      .then(function(result){
        feedback.textContent=result.data.message||result.data.error||"Unable to send request.";
        if(result.ok){form.reset();el("#lock-request-type").dispatchEvent(new Event("change",{bubbles:true}));}
      }).catch(function(){feedback.textContent="Couldn't send your request. Please try again.";})
      .finally(function(){button.disabled=false;});
  });
  renderCatalog();renderDeck();
  // Preserve direct links and GET-based move-set practice results.
  var search=new URLSearchParams(window.location.search);
  if(window.location.hash==="#practice"||search.has("round")||search.has("play")){
    setGameMode("moves");
    generateSituation();
  } else {
    setGameMode("");
  }
})();