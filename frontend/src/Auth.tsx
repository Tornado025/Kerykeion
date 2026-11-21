import { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';

type User = {user_id:string;email:string};
type Session = {enabled:boolean;user:User|null};
type Mode = 'login'|'signup'|'forgot'|'reset';
const AuthContext=createContext<{session:Session|null;refresh:()=>Promise<void>;signOut:()=>Promise<void>}|null>(null);

export async function authRequest<T>(path:string,body?:unknown):Promise<T>{
 const response=await fetch('/api/auth'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(20000)}).catch((error:Error)=>{throw new Error(error.name==='TimeoutError'?'The account service took too long. Try again.':error instanceof TypeError?'We couldn’t connect. Check your connection and try again.':error.message);});
 if(response.status===204)return undefined as T;
 if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('The account service is unavailable. Please try again.');
 const data=await response.json();
 if(!response.ok){
  const detail=typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map((d:{msg:string})=>d.msg.replace(/^Value error, /,'')).join(' '):'The request failed. Please try again.';
  throw new Error(detail);
 }
 return data as T;
}

export function AuthProvider({children}:{children:ReactNode}){
 const[session,setSession]=useState<Session|null>(null),[error,setError]=useState('');
 const refresh=async()=>{setError('');try{const value=await authRequest<Session>('/session');setSession(value);}catch(e){setSession(null);setError((e as Error).message);}};
 useEffect(()=>{
  void refresh();
  const expired=()=>{sessionStorage.setItem('session-expired','1');setSession(current=>current?{...current,user:null}:current);};
  const restored=(event:PageTransitionEvent)=>{if(event.persisted)void refresh();};
  const synced=(event:StorageEvent)=>{if(event.key==='auth-changed')void refresh();};
  window.addEventListener('auth:expired',expired);window.addEventListener('pageshow',restored);window.addEventListener('storage',synced);
  return()=>{window.removeEventListener('auth:expired',expired);window.removeEventListener('pageshow',restored);window.removeEventListener('storage',synced);};
 },[]);
 const signOut=async()=>{await authRequest('/logout',{});localStorage.setItem('auth-changed',String(Date.now()));setSession(current=>current?{...current,user:null}:current);};
 if(error)return <main className="auth-shell"><div className="brand">Kerykeion</div><h1>We couldn’t check your session</h1><p role="alert">{error}</p><button className="auth-primary" onClick={()=>void refresh()}>Try again</button></main>;
 return <AuthContext.Provider value={{session,refresh,signOut}}>{children}</AuthContext.Provider>;
}

export function AuthGate({children}:{children:ReactNode}){
 const auth=useContext(AuthContext);
 if(!auth?.session)return <main className="auth-shell"><div className="brand">Kerykeion</div><p role="status">Checking your session…</p></main>;
 if(!auth.session.enabled||auth.session.user)return children;
 return <AuthForm onAuthenticated={auth.refresh}/>;
}

export function passwordChecks(password:string){return [
 {label:'More than 8 characters (9–128)',met:password.length>=9&&password.length<=128},
 {label:'An uppercase letter (A–Z)',met:/[A-Z]/.test(password)},
 {label:'A lowercase letter (a–z)',met:/[a-z]/.test(password)},
 {label:'A number (0–9)',met:/[0-9]/.test(password)},
];}
export function PasswordStrength({password}:{password:string}){
 const checks=passwordChecks(password),valid=checks.every(check=>check.met);
 const predictable=/(password|qwerty|123456|letmein)/i.test(password)||/(.)\1{3}/.test(password);
 const score=!password?0:!valid||predictable?1:password.length<12?2:password.length<16?3:4;
 const label=['Not entered','Weak','Fair','Good','Strong'][score];
 return <div className="password-strength" id="password-rules"><div className="strength-heading"><span>Password strength</span><strong role="status" aria-live="polite">{label}</strong></div><meter min={0} max={4} value={score} low={2} high={3} optimum={4} aria-label="Password strength" aria-valuetext={label}>{label}</meter><ul>{checks.map(check=><li key={check.label} className={check.met?'requirement-met':''}><span aria-hidden="true">{check.met?'✓':'○'}</span><span className="sr-only">{check.met?'Met: ':'Required: '}</span>{check.label}</li>)}</ul><p className="auth-hint">Longer, unique passwords are harder to guess. Avoid common words and repeated characters.</p></div>;
}

export function AuthForm({onAuthenticated}:{onAuthenticated:()=>Promise<void>}){
 const submitting=useRef(false),heading=useRef<HTMLHeadingElement>(null);
 const[visible,setVisible]=useState(false),[fieldError,setFieldError]=useState('');
 const[mode,setMode]=useState<Mode>('login'),[email,setEmail]=useState(''),[password,setPassword]=useState(''),[confirm,setConfirm]=useState(''),[code,setCode]=useState('');
 const[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[resendAt,setResendAt]=useState(0),[now,setNow]=useState(Date.now());
 useEffect(()=>{document.title=(mode==='login'?'Sign in':mode==='signup'?'Create account':'Reset password')+' · Kerykeion';heading.current?.focus();},[mode]);
 useEffect(()=>{if(sessionStorage.getItem('session-expired')){setNotice('Your session expired. Sign in to continue.');sessionStorage.removeItem('session-expired');}},[]);
 useEffect(()=>{if(!resendAt)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[resendAt]);
 const switchMode=(next:Mode)=>{setMode(next);setVisible(false);setFieldError('');setPassword('');setConfirm('');setCode('');setError('');setNotice('');};
 const sendCode=async()=>{const result=await authRequest<{message:string}>('/forgot-password',{email});setNotice(result.message);setResendAt(Date.now()+60000);setNow(Date.now());setMode('reset');};
 const submit=async(event:FormEvent)=>{
  event.preventDefault();if(submitting.current)return;submitting.current=true;setFieldError('');setError('');setNotice('');setBusy(true);
  try{
   if((mode==='signup'||mode==='reset')&&!passwordChecks(password).every(check=>check.met)){setFieldError('password');throw new Error('Use 9–128 characters with an uppercase letter, a lowercase letter and a number.');}
   if((mode==='signup'||mode==='reset')&&password!==confirm){setFieldError('confirm');throw new Error('The passwords do not match.');}
   if(mode==='forgot')await sendCode();
   else if(mode==='reset'){const result=await authRequest<{message:string}>('/reset-password',{email,code,password});switchMode('login');setNotice(result.message);}
   else{await authRequest('/'+mode,{email,password});localStorage.setItem('auth-changed',String(Date.now()));await onAuthenticated();}
  }catch(e){setError((e as Error).message);requestAnimationFrame(()=>document.getElementById('auth-error')?.focus());}finally{submitting.current=false;setBusy(false);}
 };
 const resend=async()=>{setError('');setBusy(true);try{await sendCode();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 const seconds=Math.max(0,Math.ceil((resendAt-now)/1000));
 const titles={login:'Sign in to Kerykeion',signup:'Create your account',forgot:'Forgot your password?',reset:'Choose a new password'};
 return <main className="auth-shell"><div className="brand">Kerykeion</div><section className="auth-content" aria-labelledby="auth-title">
  <h1 ref={heading} tabIndex={-1} id="auth-title">{titles[mode]}</h1><p className="auth-intro">{mode==='login'?'Continue exploring variant histories and predictions.':mode==='signup'?'Keep access to the ClinVar research workspace.':mode==='forgot'?'Enter your account email to receive a six-digit reset code.':`Enter the code sent to ${email} and set a new password.`}</p>
  {notice&&<p className="auth-notice" role="status">{notice}</p>}{error&&<p id="auth-error" tabIndex={-1} className="auth-error" role="alert">{error}</p>}
  <form onSubmit={submit} className="auth-form" aria-busy={busy}>
   {mode!=='reset'&&<label>Email address<input type="email" autoComplete="email" name="email" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)} disabled={busy}/></label>}
   {mode==='reset'&&<label>Reset code<input type="text" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,''))} disabled={busy}/></label>}

   {mode!=='forgot'&&<label>{mode==='reset'?'New password':'Password'}<input type={visible?'text':'password'} aria-invalid={fieldError==='password'||undefined} aria-describedby={mode==='signup'||mode==='reset'?'password-rules'+(fieldError==='password'?' auth-error':''):undefined} name="password" autoComplete={mode==='login'?'current-password':'new-password'} required minLength={mode==='login'?1:9} pattern={mode==='login'?undefined:'(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9]).{9,128}'} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/></label>}
   {(mode==='signup'||mode==='reset')&&<><PasswordStrength password={password}/><label>Confirm password<input type={visible?'text':'password'} aria-invalid={fieldError==='confirm'||undefined} aria-describedby={fieldError==='confirm'?'auth-error':undefined} name="confirm" autoComplete="new-password" required minLength={9} maxLength={128} value={confirm} onChange={e=>setConfirm(e.target.value)} disabled={busy}/></label></>}
   {(mode==='login'||mode==='signup')&&<button type="button" className="password-toggle text-action" aria-pressed={visible} onClick={()=>setVisible(v=>!v)}>{visible?'Hide password':'Show password'}</button>}
   <button className="auth-primary" type="submit" disabled={busy}>{busy?(mode==='login'?'Signing in…':mode==='signup'?'Creating account…':'Please wait…'):mode==='login'?'Sign in':mode==='signup'?'Create account':mode==='forgot'?'Send reset code':'Update password'}</button>
  </form>
  <div className="auth-actions">{mode==='login'?<><button onClick={()=>switchMode('forgot')} disabled={busy}>Forgot password?</button><span>New here? <button onClick={()=>switchMode('signup')} disabled={busy}>Create an account</button></span></>:<button onClick={()=>switchMode('login')} disabled={busy}>Back to sign in</button>}
  {mode==='reset'&&<><button onClick={()=>void resend()} disabled={busy||seconds>0}>{seconds?`Resend code in ${seconds}s`:'Resend code'}</button><button onClick={()=>switchMode('forgot')} disabled={busy}>Use a different email</button></>}</div>
 </section><p className="auth-footnote">ClinVar release histories for BRCA1, BRCA2 and TP53.</p><PrivacyHelp/></main>;
}

export function AccountMenu(){
 const auth=useContext(AuthContext),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 if(!auth?.session?.enabled||!auth.session.user)return null;
 const logout=async()=>{setBusy(true);setError('');try{await auth.signOut();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 return <details className="account-menu"><summary>Account</summary><div><span>{auth.session.user.email}</span><button className="text-action" onClick={()=>void logout()} disabled={busy}>{busy?'Signing out…':'Sign out'}</button>{error&&<span role="alert">{error}</span>}</div></details>;
}

export function PrivacyHelp(){return <details className="privacy-help"><summary>Privacy and help</summary><p>This research prototype explores public ClinVar records for BRCA1, BRCA2 and TP53. Do not enter patient information. Predictions support research review and do not establish clinical significance.</p><p>Account information includes your email address, a password hash and session records. Signing out ends the current session. Ask the project maintainer about account access, data removal or a problem with the workspace.</p></details>;}
