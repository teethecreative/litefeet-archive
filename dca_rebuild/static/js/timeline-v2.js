/* Unified LiteFeet chronology — progressive public entries, attributed sources. */
(() => {
"use strict";
const root=document.querySelector("[data-unified-timeline]");
if(!root||typeof fetch!=="function")return;
const form=root.querySelector("[data-timeline-search]");
const list=root.querySelector("[data-timeline-list]");
const more=root.querySelector("[data-timeline-more]");
const state=root.querySelector("[data-timeline-state]");
const count=root.querySelector("[data-timeline-count]");
const empty=root.querySelector("[data-timeline-empty]");
let page=Math.max(1,Number(new URLSearchParams(location.search).get("page"))||1);
let hasMore=!more.hidden,busy=false,observer;
function addSources(parent,sources){
 const line=document.createElement("p");line.className="lfv-unified-source";
 sources.forEach((source,i)=>{if(i)line.append(document.createTextNode(" · "));
 const a=document.createElement("a");a.href=source.url;a.target="_blank";a.rel="noopener noreferrer";
 a.textContent=source.title+" ↗";line.append(a);});parent.append(line);
}
function make(entry){
 const row=document.createElement("article");row.className="lfv-unified-item";row.setAttribute("role","listitem");
 const meta=document.createElement("p");meta.className="lfv-unified-meta";
 meta.textContent=(entry.period||"DATE UNDER REVIEW")+" / "+entry.collection;row.append(meta);
 if(entry.kind==="chapter"||entry.kind==="milestone"||entry.kind==="era"){
  const details=document.createElement("details");details.className="lfv-unified-expand";
  const summary=document.createElement("summary");const heading=document.createElement("strong");heading.textContent=entry.title;
  const plus=document.createElement("span");plus.textContent="+";plus.setAttribute("aria-hidden","true");summary.append(heading,plus);details.append(summary);
  if(entry.kind==="chapter"){
    const intro=document.createElement("p");intro.className="lfv-unified-summary";intro.textContent=entry.summary;details.append(intro);
    (entry.detail||[]).forEach(part=>{const box=document.createElement("div");box.className="lfv-unified-evidence";
      const paragraph=document.createElement("p");paragraph.textContent=part.text;box.append(paragraph);addSources(box,part.sources||[]);details.append(box);});
  }else {if(entry.summary){const info=document.createElement("p");info.className="lfv-unified-summary";info.textContent=entry.summary;details.append(info);}if(entry.sources&&entry.sources.length)addSources(details,entry.sources);}
  row.append(details);
 } else {
  const h=document.createElement("h3");const link=document.createElement("a");link.href=entry.href;link.textContent=entry.title;h.append(link);row.append(h);
  if(entry.summary){const descr=document.createElement("p");descr.className="lfv-unified-summary";descr.textContent=entry.summary;row.append(descr);}
  const links=document.createElement("div");links.className="lfv-unified-row-links";
  const open=document.createElement("a");open.href=entry.href;open.textContent="VIEW RECORD →";links.append(open);
  if(entry.sources&&entry.sources.length){const moreSources=document.createElement("details");const su=document.createElement("summary");
    su.textContent="SOURCES ("+entry.sources.length+")";moreSources.append(su);addSources(moreSources,entry.sources);links.append(moreSources);}
  row.append(links);
 }
 return row;
}
async function load(next,replace){
 if(busy||(!hasMore&&!replace))return;busy=true;more.disabled=true;state.textContent="LOADING RECORDS…";
 const data=new FormData(form),params=new URLSearchParams({page:String(next),q:String(data.get("q")||"").slice(0,120),collection:String(data.get("collection")||"all"),timeline:"1"});
 try{
  const response=await fetch("/archive/api/records?"+params.toString(),{credentials:"same-origin",headers:{Accept:"application/json"}});
  if(!response.ok)throw new Error("Timeline unavailable");
  const result=await response.json(),fragment=document.createDocumentFragment();
  (result.records||[]).forEach(item=>fragment.append(make(item)));
  if(replace)list.replaceChildren();list.append(fragment);
  page=result.page;hasMore=Boolean(result.has_more);more.hidden=!hasMore;
  empty.hidden=result.total!==0;count.textContent=result.total+" ENTRIES";
  state.textContent=hasMore?"SCROLL FOR MORE":"ALL RECORDS LOADED";
  if(replace){const url=new URL(location.href);url.searchParams.delete("page");
    params.get("q")?url.searchParams.set("q",params.get("q")):url.searchParams.delete("q");
    params.get("collection")!=="all"?url.searchParams.set("collection",params.get("collection")):url.searchParams.delete("collection");
    history.replaceState(null,"",url);}
 }catch(_){state.textContent="COULD NOT LOAD RECORDS. TRY AGAIN.";more.hidden=false;hasMore=true;}
 finally{busy=false;more.disabled=false;}
}
more.addEventListener("click",()=>load(page+1,false));
form.addEventListener("submit",event=>{event.preventDefault();hasMore=true;load(1,true);});
if("IntersectionObserver" in window){observer=new IntersectionObserver(items=>{if(items.some(x=>x.isIntersecting)&&hasMore&&!busy)load(page+1,false);},{rootMargin:"160px 0px"});observer.observe(more);}
})();