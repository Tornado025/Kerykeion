import { afterEach,expect,it,vi } from 'vitest';
import { act,fireEvent,cleanup,render,screen,renderHook,waitFor } from '@testing-library/react';
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

const releases=[{release_id:1,label:'2025-01',provenance:'clinvar_archive'},{release_id:2,label:'2025-02',provenance:'clinvar_archive'}];
const json=(data:unknown)=>new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
it('keeps the release selector mounted and future release links usable while switching',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{
  if(url==='/api/releases')return json(releases);
  if(url.includes('/provenance'))return json([]);
  if(url.includes('release=2'))return new Promise<Response>(()=>{});
  return json({variant:{variant_id:7,gene_symbol:'BRCA1',variant_name:'Historical variant'},assertions:[],events:[],predictions:[],states:[{release_id:1,label:'2025-01',aggregate_class:'V',review_stars:0}],validation:null});
 }));
 render(<MemoryRouter initialEntries={['/variant.html?id=7&release=1']}><App/></MemoryRouter>);
 expect(await screen.findByText('Historical variant')).toBeVisible();
 expect(screen.getByRole('link',{name:/2025-02: View release/})).toHaveAttribute('href','/variant.html?id=7&release=2');
 const picker=screen.getByLabelText('Observed release');
 fireEvent.change(picker,{target:{value:'2'}});
 expect(screen.getByLabelText('Observed release')).toBe(picker);
 expect(screen.queryByText('Historical variant')).not.toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Explore'})).toHaveAttribute('href','/?release=2');
 fireEvent.change(picker,{target:{value:'1'}});
 expect(await screen.findByText('Historical variant')).toBeVisible();
});
it('ignores an aborted request that fails after its replacement succeeds',async()=>{
 let rejectOld!:(reason:Error)=>void;
 vi.stubGlobal('fetch',vi.fn((url:string)=>url.endsWith('old')?new Promise<Response>((_,reject)=>{rejectOld=reject;}):Promise.resolve(json({marker:'current'}))));
 const{result,rerender}=renderHook(({path}:{path:string})=>useResource<{marker:string}>(path),{initialProps:{path:'/old'}});
 rerender({path:'/current'});
 await waitFor(()=>expect(result.current.data?.marker).toBe('current'));
 await act(async()=>{rejectOld(new Error('Late network failure'));});
 expect(result.current.error).toBe('');expect(result.current.data?.marker).toBe('current');
});
it('resets gene pagination on a release switch and preserves that release on return links',async()=>{
 const requests:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{
  requests.push(url);
  if(url==='/api/releases')return json(releases);
  const p=new URL(url,'http://localhost').searchParams;
  const rid=Number(p.get('release'));const offset=Number(p.get('offset'));
  return json({release:releases[rid-1],variants:[{variant_id:100+offset,variant_name:`Release ${rid} row ${offset}`,aggregate_class:'V',submitter_count:2}],total:200});
 }));
 render(<MemoryRouter initialEntries={['/gene.html?symbol=BRCA1&release=2']}><App/></MemoryRouter>);
 expect(await screen.findByText('Release 2 row 0')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Next'}));
 expect(await screen.findByText('Release 2 row 80')).toBeVisible();
 fireEvent.change(screen.getByLabelText('Observed release'),{target:{value:'1'}});
 expect(await screen.findByText('Release 1 row 0')).toBeVisible();
 expect(requests.some(url=>url.includes('release=1')&&url.includes('offset=80'))).toBe(false);
 expect(screen.getByRole('link',{name:'Back to genes'})).toHaveAttribute('href','/?release=1');
});

it('keeps March and every imported month visible when February is selected',async()=>{
 const months=[...releases,{release_id:3,label:'2025-03',provenance:'clinvar_archive'}];
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url==='/api/releases'?months:{release:releases[1],genes:[]})));
 render(<MemoryRouter initialEntries={['/?release=2']}><App/></MemoryRouter>);
 expect(await screen.findByRole('button',{name:'2025-02'})).toHaveAttribute('aria-pressed','true');
 fireEvent.click(screen.getByRole('button',{name:'2025-01'}));
 expect(screen.getByRole('button',{name:'2025-02'})).toBeVisible();
 expect(screen.getByRole('button',{name:'2025-03'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'2025-03'}));
 expect(screen.getByRole('button',{name:'2025-03'})).toHaveAttribute('aria-pressed','true');
 expect(screen.getByRole('button',{name:'2025-01'})).toBeVisible();
});
it('explains that a no-change audit run has no meaningful priority ordering',async()=>{
 const model={model_id:1,model_name:'no_change',origin_release_id:2,label:'2025-02',horizon:1,feature_set:'static',metadata:{},metrics:null};
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url==='/api/releases'?releases:url==='/api/models'?[model]:{model,predictions:[],total:10,budget_count:1})));
 render(<MemoryRouter initialEntries={['/audit.html?model=1']}><App/></MemoryRouter>);
 expect(await screen.findByText(/Every score in this baseline is zero/)).toBeInTheDocument();
 expect(screen.getByText('Which variants might change next?')).toBeVisible();
 fireEvent.click(screen.getByText('Technical details and comparison methods'));
 expect(screen.getByText('None — fixed comparison rule')).toBeVisible();
 expect(screen.getByRole('button',{name:'2025-01'})).toBeVisible();
});
it('explains model inputs, the target and evaluation metrics on the models page',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url==='/api/releases'?releases:[])));
 render(<MemoryRouter initialEntries={['/benchmark.html']}><App/></MemoryRouter>);
 expect(screen.getByText('Are the predictions working?')).toBeVisible();
 expect(screen.getByText('What are we building?')).toBeVisible();
 expect(screen.getByText(/We have not established a reliable winner yet/)).toBeVisible();
 expect(screen.getByText('Predict the next month.')).toBeVisible();
 await screen.findByText('No prediction tests have been saved yet.');
});
it('keeps the imported release catalogue available if a background refresh fails',async()=>{
 let calls=0;
 vi.stubGlobal('fetch',vi.fn(async()=>{if(calls++)throw new Error('Temporary network failure');return json(releases);}));
 const{result}=renderHook(()=>useResource<typeof releases>('/releases'));
 await waitFor(()=>expect(result.current.data).toHaveLength(2));
 act(()=>result.current.retry());
 await waitFor(()=>expect(result.current.error).toBe('Temporary network failure'));
 expect(result.current.data).toHaveLength(2);
});
