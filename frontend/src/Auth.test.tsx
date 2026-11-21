import { afterEach,expect,it,vi } from 'vitest';
import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react';
import { AuthForm,AuthGate,AuthProvider,PasswordStrength } from './Auth';

afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const json=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
it('keeps research content hidden until the server confirms a session',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>json({enabled:true,user:null})));
 render(<AuthProvider><AuthGate><div>Private research workspace</div></AuthGate></AuthProvider>);
 expect(screen.queryByText('Private research workspace')).not.toBeInTheDocument();
 expect(await screen.findByRole('heading',{name:'Sign in to Kerykeion'})).toBeVisible();
});
it('uses email and password for login and refreshes the server session',async()=>{
 const refresh=vi.fn(async()=>{});const fetcher=vi.fn(async(_url:string,_options?:RequestInit)=>json({user:{email:'a@example.com',user_id:'1'}}));vi.stubGlobal('fetch',fetcher);
 render(<AuthForm onAuthenticated={refresh}/>);
 fireEvent.change(screen.getByLabelText('Email address'),{target:{value:'a@example.com'}});
 fireEvent.change(screen.getByLabelText('Password'),{target:{value:'a long password'}});
 fireEvent.click(screen.getByRole('button',{name:'Sign in'}));
 await waitFor(()=>expect(refresh).toHaveBeenCalledOnce());
 expect(fetcher.mock.calls[0][0]).toBe('/api/auth/login');
 expect(JSON.parse(fetcher.mock.calls[0][1]!.body as string)).toEqual({email:'a@example.com',password:'a long password'});
});
it('shows an email reset-code form and returns to login after changing the password',async()=>{
 const calls:{url:string;body:Record<string,string>}[]=[];
 vi.stubGlobal('fetch',vi.fn(async(url:string,options:RequestInit)=>{calls.push({url,body:JSON.parse(options.body as string)});return json({message:url.endsWith('forgot-password')?'If an account exists, a code will be sent.':'Password updated. Sign in with your new password.'});}));
 render(<AuthForm onAuthenticated={async()=>{}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Forgot password?'}));
 fireEvent.change(screen.getByLabelText('Email address'),{target:{value:'a@example.com'}});
 fireEvent.click(screen.getByRole('button',{name:'Send reset code'}));
 expect(await screen.findByLabelText('Reset code')).toBeVisible();
 expect(screen.getByRole('button',{name:/Resend code in/})).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Reset code'),{target:{value:'123456'}});
 fireEvent.change(screen.getByLabelText('New password'),{target:{value:'A changed long password 7'}});
 fireEvent.change(screen.getByLabelText('Confirm password'),{target:{value:'A changed long password 7'}});
 fireEvent.click(screen.getByRole('button',{name:'Update password'}));
 expect(await screen.findByRole('heading',{name:'Sign in to Kerykeion'})).toBeVisible();
 expect(calls[1]).toEqual({url:'/api/auth/reset-password',body:{email:'a@example.com',code:'123456',password:'A changed long password 7'}});
 expect(screen.getByLabelText('Password')).toHaveValue('');
});
it('clears private content when an API request reports an expired session',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>json({enabled:true,user:{email:'a@example.com',user_id:'1'}})));
 render(<AuthProvider><AuthGate><div>Private research workspace</div></AuthGate></AuthProvider>);
 expect(await screen.findByText('Private research workspace')).toBeVisible();
 window.dispatchEvent(new Event('auth:expired'));
 expect(await screen.findByRole('heading',{name:'Sign in to Kerykeion'})).toBeVisible();
 expect(screen.queryByText('Private research workspace')).not.toBeInTheDocument();
});
it('does not send signup when the confirmed password differs',async()=>{
 const fetcher=vi.fn();vi.stubGlobal('fetch',fetcher);render(<AuthForm onAuthenticated={async()=>{}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Create an account'}));
 fireEvent.change(screen.getByLabelText('Email address'),{target:{value:'a@example.com'}});
 fireEvent.change(screen.getByLabelText('Password'),{target:{value:'A long first password 7'}});
 fireEvent.change(screen.getByLabelText('Confirm password'),{target:{value:'A long other password 8'}});
 fireEvent.click(screen.getByRole('button',{name:'Create account'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('The passwords do not match.');expect(fetcher).not.toHaveBeenCalled();
});

it('reveals a login password without losing its value and prevents duplicate submissions',async()=>{
 const fetcher=vi.fn(()=>new Promise<Response>(()=>{}));vi.stubGlobal('fetch',fetcher);
 render(<AuthForm onAuthenticated={async()=>{}}/>);
 fireEvent.change(screen.getByLabelText('Email address'),{target:{value:'a@example.com'}});
 const password=screen.getByLabelText('Password');fireEvent.change(password,{target:{value:'a long password'}});
 fireEvent.click(screen.getByRole('button',{name:'Show password'}));
 expect(password).toHaveAttribute('type','text');expect(password).toHaveValue('a long password');
 const form=password.closest('form')!;fireEvent.submit(form);fireEvent.submit(form);
 expect(fetcher).toHaveBeenCalledOnce();
 expect(screen.getByRole('button',{name:'Signing in…'})).toBeDisabled();
});

it('updates the password meter and reports each unmet requirement',()=>{
 const {rerender}=render(<PasswordStrength password="abc"/>);
 expect(screen.getByRole('meter',{name:'Password strength'})).toHaveAttribute('aria-valuetext','Weak');
 expect(document.querySelectorAll('.requirement-met')).toHaveLength(1);
 rerender(<PasswordStrength password="River7MapleCedar!"/>);
 expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext','Strong');
 expect(document.querySelectorAll('.requirement-met')).toHaveLength(4);
});
