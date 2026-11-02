import { afterEach,expect,it,vi } from 'vitest';
import { cleanup,render,screen,renderHook,waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useResource } from './api';
import App,{percent} from './App';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('shows configured genes before an archive is published, with honest pending labels',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify(url==='/api/releases'?[]:{release:null,genes:[{gene_id:672,gene_symbol:'BRCA1',description:'BRCA1 DNA repair associated',variants:0,changed:0}]}),{headers:{'Content-Type':'application/json'}})));
 render(<MemoryRouter><App/></MemoryRouter>);
 expect(await screen.findByText('BRCA1')).toBeVisible();expect(screen.getByText('Awaiting import')).toBeVisible();expect(screen.queryByText('ClinVar Time Machine')).not.toBeInTheDocument();
});
it('distinguishes an undefined metric from a measured zero',()=>{expect(percent(null)).toBe('—');expect(percent(0)).toBe('0.0%');});

it('never displays later-release data while an earlier-release request is pending',async()=>{
 vi.stubGlobal('fetch',vi.fn((url:string)=>url.endsWith('later')?Promise.resolve(new Response(JSON.stringify({marker:'later'}),{headers:{'Content-Type':'application/json'}})):new Promise<Response>(()=>{})));
 const{result,rerender}=renderHook(({path}:{path:string})=>useResource<{marker:string}>(path),{initialProps:{path:'/later'}});
 await waitFor(()=>expect(result.current.data?.marker).toBe('later'));
 rerender({path:'/earlier'});
 expect(result.current.data).toBeNull();expect(result.current.loading).toBe(true);
});
