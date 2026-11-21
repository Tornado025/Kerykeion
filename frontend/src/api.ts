import { useEffect, useState } from 'react';
export async function get<T>(path:string,signal?:AbortSignal):Promise<T>{
 const r=await fetch('/api'+path,{signal:signal?AbortSignal.any([signal,AbortSignal.timeout(20000)]):AbortSignal.timeout(20000)}).catch((error:Error)=>{if(error.name==='TimeoutError')throw new Error('Loading took too long. Try again.');if(error instanceof TypeError)throw new Error('We couldn’t connect. Check your connection and try again.');throw error;});
 if(r.status===401){window.dispatchEvent(new Event('auth:expired'));throw new Error('Your session has expired. Sign in to continue.');}
 if(!r.headers.get('content-type')?.includes('application/json'))throw new Error('We couldn’t load these records. Try again in a moment.');
 const data=await r.json();if(!r.ok)throw new Error(data.detail||'The request failed. Try again.');return data as T;
}
export function useResource<T>(path:string|null){
 const[state,setState]=useState<{path:string|null;data:T|null;error:string;loading:boolean}>({path:null,data:null,error:'',loading:Boolean(path)});
 const[attempt,setAttempt]=useState(0);
 useEffect(()=>{
  if(!path){setState({path:null,data:null,error:'',loading:false});return;}
  const controller=new AbortController();
  setState(s=>({path,data:s.path===path?s.data:null,error:'',loading:true}));
  get<T>(path,controller.signal).then(data=>{if(!controller.signal.aborted)setState({path,data,error:'',loading:false});})
   .catch(e=>{if(!controller.signal.aborted&&e.name!=='AbortError')setState(s=>({path,data:s.path===path?s.data:null,error:e.message,loading:false}));});
  return()=>controller.abort();
 },[path,attempt]);
 const matches=state.path===path;
 return{data:matches?state.data:null,error:matches?state.error:'',loading:Boolean(path)&&(!matches||state.loading),retry:()=>setAttempt(x=>x+1)};
}
