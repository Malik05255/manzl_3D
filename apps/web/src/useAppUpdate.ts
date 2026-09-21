import { useEffect,useRef,useState } from "react";

function currentBundle(){
  const scripts=[...document.querySelectorAll<HTMLScriptElement>("script[src]")];
  return scripts.map(script=>new URL(script.src,location.href).pathname).filter(path=>path.includes("/assets/")).sort().join("|");
}

async function remoteBundle(){
  const response=await fetch(`/?__manzil_update=${Date.now()}`,{cache:"no-store",headers:{"cache-control":"no-cache"}});
  if(!response.ok)return "";
  const html=await response.text();
  const doc=new DOMParser().parseFromString(html,"text/html");
  return [...doc.querySelectorAll<HTMLScriptElement>("script[src]")]
    .map(script=>new URL(script.getAttribute("src")??"",location.href).pathname)
    .filter(path=>path.includes("/assets/"))
    .sort()
    .join("|");
}

export function useAppUpdate(){
  const[registration,setRegistration]=useState<ServiceWorkerRegistration|null>(null);
  const[updateReady,setUpdateReady]=useState(false);
  const bundleRef=useRef("");

  useEffect(()=>{
    if(import.meta.env.DEV)return;
    bundleRef.current=currentBundle();

    let disposed=false;
    const check=async()=>{
      try{
        const remote=await remoteBundle();
        if(!disposed&&remote&&bundleRef.current&&remote!==bundleRef.current)setUpdateReady(true);
      }catch{}
    };

    void check();
    const timer=window.setInterval(check,15*60*1000);
    const onVisible=()=>{if(document.visibilityState==="visible")void check();};
    document.addEventListener("visibilitychange",onVisible);

    if("serviceWorker" in navigator){
      navigator.serviceWorker.register("/sw.js").then(reg=>{
        if(disposed)return;
        setRegistration(reg);
        if(reg.waiting)setUpdateReady(true);
        reg.addEventListener("updatefound",()=>{
          const worker=reg.installing;
          if(!worker)return;
          worker.addEventListener("statechange",()=>{
            if(worker.state==="installed"&&navigator.serviceWorker.controller)setUpdateReady(true);
          });
        });
      }).catch(()=>undefined);
    }

    return()=>{
      disposed=true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange",onVisible);
    };
  },[]);

  const installUpdate=()=>{
    if(registration?.waiting){
      registration.waiting.postMessage({type:"SKIP_WAITING"});
      const reload=()=>window.location.reload();
      navigator.serviceWorker.addEventListener("controllerchange",reload,{once:true});
      window.setTimeout(reload,1200);
      return;
    }
    window.location.reload();
  };

  return{updateReady,installUpdate};
}
