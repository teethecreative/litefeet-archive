/* Lock In demo battle table. Unspecified scoring stays manual, not invented. */
(function () {
  "use strict";
  var root=document.getElementById("lock-workbench");
  if(!root)return;
  var samples=JSON.parse(document.getElementById("lock-samples").textContent);
  var types=["Dancer","Arena","Producer","Song","Move","Trick","Upgrade","Frib"];
  var all=samples.map(function(s){return s.categories.reduce(function(a,g){return a.concat(g.cards.map(function(n){return {id:g.type+"::"+n,type:g.type,name:n};}));},[]);});
  var pool={}; all.forEach(function(a){a.forEach(function(c){pool[c.id]=c;});});
  var deck=all[0].slice(),stage="setup",round=1,hand=[],selected=[],history=[];
  function el(s){return root.querySelector(s);}
  function escape(s){return String(s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
  function amount(id){return deck.filter(function(c){return c.id===id;}).length;}
  function limits(){return deck.every(function(c){return amount(c.id)<=3;});}
  function problems(){
    var p=[];
    if(deck.length<25||deck.length>50)p.push("A deck must contain 25–50 total cards.");
    if(!limits())p.push("A card cannot appear more than three times.");
    ["Dancer","Song","Arena"].forEach(function(t){if(!deck.some(function(c){return c.type===t;}))p.push("A "+t+" card is required for this 1v1 setup.");});
    return p;
  }
  function options(t){
    var seen={};
    return deck.filter(function(c){if(c.type!==t||seen[c.id])return false;seen[c.id]=true;return true;}).map(function(c){return '<option value="'+escape(c.id)+'">'+escape(c.name)+'</option>';}).join("");
  }
  function renderDeck(){
    el("#lock-count").textContent=deck.length;
    el("#lock-categories").textContent=types.filter(function(t){return deck.some(function(c){return c.type===t;});}).map(function(t){return t+": "+deck.filter(function(c){return c.type===t;}).length;}).join(" · ");
    var counts={};deck.forEach(function(c){counts[c.id]=(counts[c.id]||0)+1;});
    el("#lock-deck-list").innerHTML=Object.keys(counts).map(function(id){
      var c=pool[id];return '<li><span>'+escape(c.type)+' · '+escape(c.name)+' ×'+counts[id]+'</span> <button data-remove="'+escape(id)+'" type="button" aria-label="Remove '+escape(c.name)+'">−</button><button data-add="'+escape(id)+'" type="button" '+(counts[id]>=3?"disabled":"")+' aria-label="Add '+escape(c.name)+'">+</button></li>';
    }).join("");
    var p=problems();el("#lock-validation").textContent=p.length?p.join(" "):"Deck meets the size and general three-copy limits.";
    el("#lock-start").disabled=!!p.length;
  }
  function renderCatalog(){
    var type=el("#lock-filter").value;
    el("#lock-catalog").innerHTML=Object.keys(pool).filter(function(id){return type==="all"||pool[id].type===type;}).map(function(id){return '<option value="'+escape(id)+'">'+escape(pool[id].type+" · "+pool[id].name)+'</option>';}).join("");
  }
  function shuffle(cards){var a=cards.slice();for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),x=a[i];a[i]=a[j];a[j]=x;}return a;}
  function cardName(id){return pool[id]?pool[id].name:"";}
  function drawBattle(){
    var table=el("#lock-battle");table.hidden=false;
    table.innerHTML='<h3>Round '+round+' · Arena and card setup</h3><p>Shuffle and cut the decks, then spin the adidas counter. Record the first turn below; a physical spin is not simulated.</p>'+
      '<label>Dancer <select id="lock-dancer">'+options("Dancer")+'</select></label>'+
      '<label>Song <select id="lock-song">'+options("Song")+'</select></label>'+
      '<label>Arena <select id="lock-arena">'+options("Arena")+'</select></label>'+
      '<label>Producer <select id="lock-producer"><option value="">None</option>'+options("Producer")+'</select></label>'+
      '<label>Who goes first? <select id="lock-order"><option>You</option><option>Opponent</option></select></label>'+
      '<button id="lock-draw" type="button">Set cards and draw hand</button>';
  }
  function renderHand(){
    var table=el("#lock-battle");
    table.innerHTML='<h3>Round '+round+' · Move set</h3><p>'+escape(el("#lock-dancer")?el("#lock-dancer").value:"")+'</p>'+
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
    if(e.target.id==="lock-sample"){deck=all[Number(e.target.value)].slice();el("#lock-battle").hidden=true;renderDeck();}
    if(e.target.id==="lock-filter")renderCatalog();
    if(e.target.hasAttribute("data-pick")){
      var i=Number(e.target.getAttribute("data-pick")),isMove=hand[i].type==="Move";
      if(e.target.checked){if(isMove&&selected.filter(function(j){return hand[j].type==="Move";}).length>=3){e.target.checked=false;return;}selected.push(i);}
      else selected=selected.filter(function(j){return j!==i;});
      el("#lock-selection").textContent=selected.filter(function(j){return hand[j].type==="Move";}).length+" / 3 moves selected";
    }
  });
  root.addEventListener("click",function(e){
    var b=e.target.closest("button");if(!b)return;
    if(b.hasAttribute("data-remove")){var id=b.getAttribute("data-remove"),i=deck.findIndex(function(c){return c.id===id;});if(i>=0)deck.splice(i,1);renderDeck();return;}
    if(b.hasAttribute("data-add")){var id=b.getAttribute("data-add");if(amount(id)<3)deck.push(pool[id]);renderDeck();return;}
    if(b.id==="lock-add"){var id=el("#lock-catalog").value;if(id&&amount(id)<3)deck.push(pool[id]);renderDeck();}
    if(b.id==="lock-start"){if(!problems().length){round=1;history=[];drawBattle();}}
    if(b.id==="lock-draw"){
      var played=[el("#lock-dancer").value,el("#lock-song").value,el("#lock-arena").value,el("#lock-producer").value];
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
      var outcome=p<50?"Automatic loss — your BP below 50":q<50?"Opponent automatic loss":el("#lock-draw-loss").checked||el("#lock-tko").checked?"Win by adjudicated special condition":p>q?"You win":p<q?"Opponent wins":"Tie — Round of Fire draft";
      history.push("Round "+round+": "+p+" to "+q+" BP · "+outcome);
      el("#lock-battle").innerHTML='<h3>Round result</h3><p>'+escape(outcome)+'</p><p>'+history.map(escape).join("<br>")+'</p><p>Battle victory thresholds are still blank in the rulebook; this does not claim an official battle winner.</p><button type="button" id="lock-next">Next round</button>';
    }
    if(b.id==="lock-next"){round++;drawBattle();}
  });
  el("#lock-sample").innerHTML=samples.map(function(s,i){return '<option value="'+i+'">'+escape(s.name)+'</option>';}).join("");
  el("#lock-filter").innerHTML='<option value="all">All types</option>'+types.map(function(t){return '<option value="'+t+'">'+t+'</option>';}).join("");
  renderCatalog();renderDeck();
})();