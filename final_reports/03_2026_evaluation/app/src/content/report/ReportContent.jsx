import {BasketAttributionAppendix} from './BasketAttributionAppendix.jsx';
import React from 'react';
import {DataComponent,EvidenceChart,ReportSection,RichNarrative,useDataApp} from '../../data-app-public.jsx';
import plan from './plan.json';
import './report.css';
const pctFields=new Set(['Gross return','Net return','CAGR estimate','Max DD','Ann. volatility','Gross exposure','Net exposure','Cash allocation','BTC alpha / year','Mean daily','Familywise mean LB','Worst day','Daily ES95 loss','Selected net return','Reference net return','Profitable','Median net return','Median Max DD','Gross profitable','Net profitable','Median gross return','Share of cohort','BTC hold return','ETH hold return','Median BTC trailing vol','Base net return','Stressed net return','P95 volume proxy','Max volume proxy','Largest abs. coin share','Best 5 weeks share']);
const countFields=new Set(['Basket','Lookback days','Rebalance hours','Pairs','Days','Shared strata','Shared pairs','Configurations','Baskets','Invalid draws','Unknown volume events','BTC up-state days','High vol days']);
// Interval and positive/all columns contain formatted numeric strings.
const numericTextFields=new Set(['Mean 95% CI','Sharpe 95% CI','Growth 95% CI','95% CI pp','95% CI bps','2022-2023','2024-2025','Jan-Sep 2026','Positive months']);
function isNumericColumn(field,records){return pctFields.has(field)||countFields.has(field)||numericTextFields.has(field)||/^\d+ bps/.test(field)||records.some(row=>typeof row[field]==='number');}
function format(k,v){if(v==null)return k==='Cash allocation'?'Not applicable':'Unavailable';if(typeof v==='boolean')return v?'Pass':'Fail';if(pctFields.has(k)||/^\d+ bps/.test(k))return `${(v*100).toFixed(k==='Mean daily'||k==='Familywise mean LB'||(v!==0&&Math.abs(v)<0.00005)?3:2)}%`;if(typeof v==='number'){if(countFields.has(k))return v.toLocaleString('en-US',{maximumFractionDigits:0});if(/ p$/.test(k))return v.toFixed(4);return v.toFixed(2);}return String(v);}
export function ReportContent(){
 const {appTitle,reviewedRows}=useDataApp();const rows=q=>reviewedRows(q);
 const text=(id,key,qs)=><ReportSection id={id} title={key} queryId={qs[0]} queryIds={qs} sourceRowsByQuery={Object.fromEntries(qs.map(q=>[q,rows(q)]))} showHeading={false}><RichNarrative id={`${id}:body`} value={plan.narrative[key]}/></ReportSection>;
 const table=(id,q,title,fields,subset)=>{let a=subset||rows(q);const columnClasses=Object.fromEntries(fields.map(k=>[k,isNumericColumn(k,a)?'num':'']));return <DataComponent id={id} queryId={q} title={title} kind="table" sourceRows={a} displayRows={a}><div className="final-scroll"><table className="final-table" data-reviewed-rows aria-label={title}><thead><tr>{fields.map(k=><th key={k} className={columnClasses[k]}>{k}</th>)}</tr></thead><tbody>{a.map((r,i)=><tr key={i}>{fields.map(k=><td key={k} className={columnClasses[k]}>{format(k,r[k])}</td>)}</tr>)}</tbody></table></div></DataComponent>};
 const evidence=(id,q,title,value)=><DataComponent id={id} queryId={q} title={title} kind="text" sourceRows={rows(q)} displayRows={rows(q)}><RichNarrative id={`${id}:body`} value={value}/></DataComponent>;
 const pp=q=>rows(q).map(r=>({...r,'ProfitableShare':r.Profitable}));
 return <article className="report-content final-report">
 <section className="final-page" id="overview">
  <header className="report-hero"><h1 data-data-app-title>{appTitle}</h1></header>
 <RichNarrative id="attribution-edition-note" value="[Per-coin P&L and joint basket alpha/betas, with confidence intervals, for all nine frozen strategies](#basket-attribution-appendix)."/>
  {text('summary','summary',['primary','criteria','cohort','screening','execution','provenance'])}
  {text('primary-text','primary',['primary'])}
  {table('primary-table','primary','All nine: primary 20 bps results',['ID','Gross return','Net return','Gross Sharpe','Net Sharpe','CAGR estimate','Max DD','Turnover / year'])}
 </section>
 <section className="final-page" id="identities">
  {text('identity-text','identity',['identities'])}
  {table('identities-table','identities','Frozen basket membership and settings',['ID','Basket','Strategy','Lookback days','Rebalance hours','Buffer','Coins'])}
  {text('risk-text','risk',['risk'])}
  {table('risk-table','risk','Exposure, annualized volatility and descriptive BTC attribution',['ID','Ann. volatility','Gross exposure','Net exposure','Cash allocation','BTC beta','BTC alpha / year'])}
 </section>
 <section className="final-page" id="criteria">
  {text('criteria-text','criteria',['criteria'])}
  {table('criteria-table','criteria','Approved criteria and frozen turnover caps',['ID','HAC t','Bootstrap p','Holm-9 p','Economic','Statistical','DD','Turnover','TO cap / year','All criteria'])}
  {text('inference-text','inference',['uncertainty','criteria'])}
  {table('uncertainty-table','uncertainty','Approximate intervals; no OOS reselection',['ID','Mean daily','Mean 95% CI','Sharpe 95% CI','Growth 95% CI','Familywise mean LB'])}
 </section>
 <section className="final-page" id="drawdown">
  {text('drawdown-text','drawdowns',['drawdowns'])}
  {table('dd-table','drawdowns','Maximum-depth episodes; all dates UTC',['ID','Peak UTC','Trough UTC','Recovery UTC','To trough days','DD episode days'])}
  {table('tail-table','drawdowns','Additional downside and duration measures',['ID','Longest underwater days','Worst day','Daily ES95 loss'])}
  {evidence('complete-primary-evidence','all_primary','Full indicator companion','[Download all nine primary indicators](exports/nine_primary_metrics.csv), including Sortino, Calmar, ulcer index, time underwater, daily win rate, tail measures and full BTC attribution. No trade-level profit factor is fabricated without a trade-grouping definition.')}
 </section>
 <section className="final-page" id="paths">
  {text('paths-text','paths',['paths','periods'])}
  <EvidenceChart id="paths-A" queryId="paths" title="Track A: daily closing net NAV, start = 1" rows={rows('paths').filter(r=>r.ID.startsWith('A'))} sourceRows={rows('paths').filter(r=>r.ID.startsWith('A'))} height={280} spec={{type:'line',x:'Date',y:'NAV',series:'ID',stackable:false,valueDecimals:3,colors:{A01:'#245c99',A02:'#ad6d24',A03:'#2b7d64',A04:'#9d5b88'}}}/>
  <EvidenceChart id="paths-B" queryId="paths" title="Track B: daily closing net NAV, start = 1" rows={rows('paths').filter(r=>r.ID.startsWith('B'))} sourceRows={rows('paths').filter(r=>r.ID.startsWith('B'))} height={280} spec={{type:'line',x:'Date',y:'NAV',series:'ID',stackable:false,valueDecimals:3,colors:{B01:'#245c99',B03:'#ad6d24',B04:'#2b7d64',B05:'#9d5b88',B06:'#cc6d37'}}}/>
  {evidence('period-comparison-evidence','periods','Same-pair comparisons across all periods','[Download the 27 same-pair period rows](exports/nine_same_pair_periods.csv). Development, validation and partial-year evaluation remain distinct; no period has been moved to improve a result.')}
 </section>
 <section className="final-page" id="fees-nine">
  {text('stress-text','stress',['costs'])}
  {table('cost-table','costs','Net period returns under every frozen fee/delay scenario',['ID','0 bps','5 bps','10 bps','15 bps','20 bps','40 bps','20 bps +1h'])}
  {text('posthoc-text','posthoc',['neighbor_breadth','reference','a03_sides'])}
  {table('a03-sides-table','a03_sides','A03 attribution: linked contribution, not independent sleeve return',['Period','Net return','Long contribution pp','Short contribution pp','Largest abs. coin share','Best 5 weeks share','Positive months'])}
 </section>
 <section className="final-page" id="neighbors">
  {table('neighbor-table','neighbor_breadth','Positive / all pre-enumerated nearest-parameter controls',['ID','2022-2023','2024-2025','Jan-Sep 2026'])}
  {evidence('reference-evidence','reference','Same-rule reference-basket contrasts','[Download all posthoc control contrasts](exports/posthoc_control_contrasts.csv). The reference-basket and nearest-parameter comparisons are explanatory, not a new selection exercise.')}
  {text('b02-text','b02',['b02'])}
  {table('b02-table','b02','Factor-family qualification funnel',['Stage','Pairs'])}
 </section>
 <section className="final-page" id="cohort">
  {text('cohort-text','cohort',['cohort'])}
  {table('cohort-table','cohort','Exploratory 2026 constituent distributions, 20 bps',['Cohort','Pairs','Profitable','Median net return','Median Sharpe','Median Max DD','Median TO / year'])}
  <EvidenceChart id="cohort-chart" queryId="cohort" title="Profitable fraction: groups are overlapping, not additive" rows={pp('cohort')} sourceRows={rows('cohort')} height={300} spec={{type:'horizontalBar',x:'Cohort',y:'ProfitableShare',stackable:false,valueDecimals:2,colors:{ProfitableShare:'#245c99'}}}/>
  {evidence('cohort-cost-evidence','cohort_costs','All cohort fee and delay sensitivities','The source view retains every predeclared cohort fee/delay scenario. Broad and strict median zero-fee returns were still negative. [All 69,108 survivor rows](exports/all_69108_survivors.csv) and [all 39,332 strict-subgroup rows](exports/strict_39332_survivors.csv) remain in experiment-ID/basket-ID order, not OOS performance order.')}
 </section>
 <section className="final-page" id="screening">
  {text('screening-text','screening',['screening'])}
  {table('screening-table','screening','Four exploratory screening comparisons; sign = survivors minus controls',['Contrast','Lift pp','95% CI pp','Centered p','Holm-4 p','Reject 5%'])}
  {text('fees-text','fees',['fees','cohort_costs'])}
  {table('fees-table','fees','Controls traded more but had stronger pre-fee breadth',['Cohort','Gross profitable','Net profitable','Gross profit erased pp','Median gross return','Median net return','Median TO / year'])}
 </section>
 <section className="final-page" id="settings">
  {text('settings-text','settings',['family','decomposition'])}
  {table('family-table','family','Every family: no favorable family is promoted',['Family','Cohort','Pairs','Share of cohort','Profitable','Median net return','Median Sharpe'])}
  {evidence('settings-evidence','family','Settings companion','[Download all settings and subgroups](exports/all_settings_summary.csv), including the full eight trend settings and every represented configuration. An unavailable factor-survivor cell means no qualifying member, not zero performance.')}
 </section>
 <section className="final-page" id="baskets">
  {text('baskets-text','baskets',['decomposition','coins'])}
  {table('decomposition-table','decomposition','Alternative standardizations; all gaps are controls minus survivors',['Conditioning','Composition pp','Within pp','Unsupported pp','Raw gap pp','Standardized gap pp','Shared strata','Shared pairs'])}
  {text('joint-text','joint',['joint'])}
  {table('joint-table','joint','Joint additive sensitivity; not causal or an independent hypothesis test',['Pairs','Configurations','Baskets','Raw retained gap pp','Adjusted gap pp'])}
  {evidence('coin-evidence','coins','Basket composition companion','[Download historical-rank coin inclusion frequencies](exports/coin_inclusion_frequencies.csv). Historical liquidity rank is not a 2026 performance rank; fixed BTC/ETH inclusion has no identifiable contrast here.')}
 </section>
 <section className="final-page" id="regimes">
  {text('regime-text','regimes',['market','regimes'])}
  {table('market-table','market','Period context: unequal horizons, not timing signals',['Period','Days','BTC hold return','ETH hold return','Median BTC trailing vol','BTC up-state days','High vol days','Context 28d rank IC'])}
  {table('regime-table','regimes','Decision-time states versus following-day returns; gaps in bps/day',['Regime','State','Days','Raw C-S gap bps/day','Same-setting gap bps/day'])}
 </section>
 <section className="final-page" id="regime-inference">
  {text('regime-inference-text','regime_inference',['regime_tests'])}
  {table('regime-test-table','regime_tests','Regime interactions: missing evidence stays unavailable',['Regime','Interaction bps','95% CI bps','Centered p','Holm-4 p','Invalid draws','Status'])}
  {text('execution-text','execution',['execution'])}
  {table('execution-table','execution','Hypothetical stress and preceding-hour volume proxy; 100k-USDT scenario',['ID','Base net return','Stressed net return','P95 volume proxy','Max volume proxy','Unknown volume events'])}
 </section>
 <section className="final-page" id="conclusions">
  {text('conclusion-text','conclusion',['criteria','screening','regime_tests','execution','prospective'])}
  {text('provenance-text','provenance',['primary','criteria','cohort','provenance'])}
  <RichNarrative id="companions:body" value={'[Nine-case inference](exports/nine_primary_inference.csv) · [All 63 scenarios](exports/nine_all_63_scenarios.csv) · [Attribution](exports/attribution_summary.csv) · [Hypothetical carry/slippage](exports/hypothetical_carry_slippage.csv) · [Volume proxy](exports/target_volume_proxy.csv) · [Regime interactions](exports/regime_interactions.csv) · [Full regime results](exports/regime_results.csv)\n\n**Reading order:** 1. Development and robustness; 2. Validation and frozen selection; 3. This report. Companion CSVs are supporting results, not additional reports.'}/>
 </section>
 <BasketAttributionAppendix/>
 </article>;
}
