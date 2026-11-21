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
  if(url.includes('/timing?'))return json(null);
  if(url.includes('release=2'))return new Promise<Response>(()=>{});
  return json({variant:{variant_id:7,gene_symbol:'BRCA1',variant_name:'Historical variant'},assertions:[],events:[],predictions:[],states:[{release_id:1,label:'2025-01',aggregate_class:'V',review_stars:0}],validation:null});
 }));
 render(<MemoryRouter initialEntries={['/variant.html?id=7&release=1']}><App/></MemoryRouter>);
 expect(await screen.findByText('Historical variant')).toBeVisible();
 fireEvent.click(screen.getByText('Classification history'));
 expect(screen.getByRole('link',{name:/2025-02: View release/})).toHaveAttribute('href','/variant.html?id=7&release=2');
 fireEvent.click(screen.getByRole('button',{name:'View historical release'}));
 const picker=screen.getByLabelText('Historical release');
 fireEvent.change(picker,{target:{value:'latest'}});
 expect(screen.getByLabelText('Historical release')).toBe(picker);
 expect(screen.queryByText('Historical variant')).not.toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Explore'})).toHaveAttribute('href','/');
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
 fireEvent.click(screen.getByRole('button',{name:'View historical release'}));
 fireEvent.change(screen.getByLabelText('Historical release'),{target:{value:'1'}});
 expect(await screen.findByText('Release 1 row 0')).toBeVisible();
 expect(requests.some(url=>url.includes('release=1')&&url.includes('offset=80'))).toBe(false);
 expect(screen.getByRole('link',{name:'Back to genes'})).toHaveAttribute('href','/?release=1');
});

it('defaults to the latest snapshot and keeps historical selection optional',async()=>{
 const months=[...releases,{release_id:3,label:'2026-11',provenance:'clinvar_archive'}];
 const calls:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{calls.push(url);return json(url==='/api/releases'?months:{release:months[2],genes:[]});}));
 render(<MemoryRouter><App/></MemoryRouter>);
 expect(await screen.findByText('November 2026')).toBeVisible();
 expect(screen.getByText('Latest data')).toBeVisible();
 expect(screen.queryByLabelText('Historical release')).not.toBeInTheDocument();
 expect(screen.queryByRole('navigation',{name:'All imported releases'})).not.toBeInTheDocument();
 await waitFor(()=>expect(calls).toContain('/api/genes?release=3'));
 fireEvent.click(screen.getByRole('button',{name:'View historical release'}));
 const picker=screen.getByLabelText('Historical release');
 expect(picker).toHaveValue('latest');
 fireEvent.change(picker,{target:{value:'1'}});
 expect(screen.getByText('Historical view')).toBeVisible();
 expect(screen.getByRole('link',{name:'Explore'})).toHaveAttribute('href','/?release=1');
 expect(screen.getByRole('option',{name:'February 2025'})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Return to latest'}));
 expect(screen.getByText('Latest data')).toBeVisible();
 expect(screen.queryByLabelText('Historical release')).not.toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Explore'})).toHaveAttribute('href','/');
});
it('keeps an explicitly linked historical release clear without a wall of month buttons',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url==='/api/releases'?releases:{release:releases[0],genes:[]})));
 render(<MemoryRouter initialEntries={['/?release=1']}><App/></MemoryRouter>);
 expect(await screen.findByText('January 2025')).toBeVisible();
 expect(screen.getByText('Historical view')).toBeVisible();
 expect(screen.getByRole('button',{name:'Return to latest'})).toBeVisible();
 expect(screen.queryByLabelText('Historical release')).not.toBeInTheDocument();
});
it('explains that a no-change audit run has no meaningful priority ordering',async()=>{
 const model={model_id:1,model_name:'no_change',origin_release_id:2,label:'2025-02',horizon:1,feature_set:'static',metadata:{},metrics:null};
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url==='/api/releases'?releases:url==='/api/models?compact=true'?[model]:{model,predictions:[],total:10,budget_count:1})));
 render(<MemoryRouter initialEntries={['/endpoint-predictions.html?model=1']}><App/></MemoryRouter>);
 expect(await screen.findByText(/Every score in this baseline is zero/)).toBeInTheDocument();
 expect(screen.getByText('Which variants might change next?')).toBeVisible();
 fireEvent.click(screen.getByText('Technical details and comparison methods'));
 expect(screen.getByText('None — fixed comparison rule')).toBeVisible();
 expect(screen.getByRole('button',{name:'View historical release'})).toBeVisible();
});
it('explains model inputs, the target and evaluation metrics on the models page',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url==='/api/releases'?releases:url==='/api/experiments/summary'?{results:[]}:[])));
 render(<MemoryRouter initialEntries={['/endpoint-checks.html']}><App/></MemoryRouter>);
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
it('keeps the horizon control available when the chosen month has no saved prediction',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url==='/api/releases'?releases:[])));
 render(<MemoryRouter initialEntries={['/endpoint-predictions.html?release=2&horizon=3']}><App/></MemoryRouter>);
 await screen.findByText(/Predictions have not been made for this month yet/);
 expect(screen.getByLabelText('Predict ahead')).toHaveValue('3');
 fireEvent.change(screen.getByLabelText('Predict ahead'),{target:{value:'1'}});
 expect(screen.getByLabelText('Predict ahead')).toHaveValue('1');
});
it('switches prediction horizons without losing gene and classification filters',async()=>{
 const calls:string[]=[];
 const saved=[1,3].map((horizon,i)=>({model_id:i+1,model_name:'boosted',origin_release_id:2,label:'2025-02',horizon,feature_set:'temporal',metadata:{train_rows:20},metrics:null}));
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{calls.push(url);return json(url==='/api/releases'?releases:url==='/api/models?compact=true'?saved:{model:saved[0],predictions:[],total:100,budget_count:1});}));
 render(<MemoryRouter initialEntries={['/endpoint-predictions.html?release=2&classification=B&gene=BRCA1']}><App/></MemoryRouter>);
 await screen.findByText('2025-03');
 fireEvent.change(screen.getByLabelText('Predict ahead'),{target:{value:'3'}});
 expect(await screen.findByText('2025-05')).toBeVisible();
 await waitFor(()=>expect(calls.some(url=>url.includes('/audit-queue?model=2')&&url.includes('classification=B')&&url.includes('gene=BRCA1'))).toBe(true));
 expect(screen.getByLabelText('Current classification')).toHaveValue('B');
 expect(screen.getByLabelText('Gene')).toHaveValue('BRCA1');
});

it('explains conditional timing and does not invent a confident month',async()=>{
 const run={run_id:7,origin_release_id:2,label:'2025-02',method:'boosted_hazard'};
 const row={variant_id:100,variant_name:'Timing example',gene_symbol:'BRCA1',aggregate_class:'V',review_rank:1,change_probability:.02,expected_month_if_change:3.4,median_month:null,event_probabilities:[.01,.005,.005,.004,.003,.003],cumulative_probabilities:[.01,.015,.02,.024,.027,.03]};
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url==='/api/releases'?releases:url==='/api/timing/runs'?[run]:{run,predictions:[row],total:100,budget_count:1,months:3})));
 render(<MemoryRouter initialEntries={['/audit.html?release=2']}><App/></MemoryRouter>);
 expect(await screen.findByText('Timing example')).toBeVisible();
 expect(screen.getByText('About 3.4 months')).toBeVisible();
 expect(screen.getByText('2.0%')).toBeVisible();
 fireEvent.click(screen.getByText('See possible timing'));
 expect(screen.getByText(/No median change month is supported/)).toBeVisible();
 expect(screen.getByText(/No change within 6 months: 97.0%/)).toBeVisible();
});

it('canonicalises an explicitly linked model to its own month and horizon',async()=>{
 const model={model_id:9,model_name:'logistic',origin_release_id:1,label:'2025-01',horizon:3,feature_set:'static',metadata:{},metrics:null};
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url==='/api/releases'?releases:url==='/api/models?compact=true'?[model]:{model,predictions:[],total:0,budget_count:0})));
 render(<MemoryRouter initialEntries={['/endpoint-predictions.html?model=9']}><App/></MemoryRouter>);
 expect(await screen.findByText('January 2025')).toBeVisible();
 expect(await screen.findByText('2025-04')).toBeVisible();
 expect(screen.getByLabelText('Predict ahead')).toHaveValue('3');
 expect(screen.queryByText('Latest data')).not.toBeInTheDocument();
});

it('pages timing results and resets the page when filters change',async()=>{
 const calls:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{calls.push(url);const offset=Number(new URL(url,'http://localhost').searchParams.get('offset'));return json(url==='/api/releases'?releases:url==='/api/timing/runs'?[]:{run:{run_id:1,origin_release_id:2,label:'2025-02'},predictions:Array.from({length:offset?5:100},(_,i)=>({variant_id:offset+i,variant_name:`Record ${offset+i}`,gene_symbol:'BRCA1',aggregate_class:'V',review_rank:offset+i+1,change_probability:.02,expected_month_if_change:3,event_probabilities:[],cumulative_probabilities:[]})),total:1000,budget_count:105});}));
 render(<MemoryRouter initialEntries={['/audit.html']}><App/></MemoryRouter>);
 await screen.findByText('Record 0');
 fireEvent.click(screen.getByRole('button',{name:'Next page'}));
 await screen.findByText('Record 100');
 expect(screen.getByRole('button',{name:'Next page'})).toBeDisabled();
 expect(screen.getByText('101–105 of 105')).toBeVisible();
 fireEvent.change(screen.getByLabelText('Gene'),{target:{value:'BRCA1'}});
 await waitFor(()=>expect(calls.some(x=>x.includes('gene=BRCA1')&&x.includes('offset=0'))).toBe(true));
});
