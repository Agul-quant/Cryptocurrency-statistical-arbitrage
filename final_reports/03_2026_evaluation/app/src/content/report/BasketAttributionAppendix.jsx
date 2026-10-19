import React from 'react';
import {DataComponent, ReportSection, RichNarrative, useDataApp} from '../../data-app-public.jsx';
import './basket-attribution.css';
const PREFIX='basket-attribution-20261016';
const cols=['Coin','Gross pp','Fees pp','Net pp','Net 95% CI (pp)','Joint beta [95% CI]'];
function FactorTable({columns,rows,label,compact=false}){return <div className="basket-factor-scroll"><table className={`basket-factor-table${compact?' basket-factor-compact':''}`} data-reviewed-rows aria-label={label}><thead><tr>{columns.map((c,j)=><th key={c} className={j?'numeric':''}>{c}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{columns.map((c,j)=><td key={c} className={j?'numeric':''}>{r[c]??'Unavailable'}</td>)}</tr>)}</tbody></table></div>}
export function BasketAttributionAppendix(){
 const {reviewedRows}=useDataApp();
 const summary=reviewedRows('basket_attribution_summary');const coins=reviewedRows('basket_attribution_coins');
 const diagnostics=reviewedRows('basket_attribution_diagnostics');const methods=reviewedRows('basket_attribution_methods');
 const overviewCols=['ID','Joint alpha / yr [95% CI]','BTC alpha / yr [95% CI]','Matched BTC alpha / yr [95% CI]','Fit / calendar days','R²','Max VIF'];
 const note=methods[0];
 const N=({id,qs,rs,text})=><ReportSection id={`${PREFIX}-${id}`} title={id} queryId={qs[0]} queryIds={qs} sourceRowsByQuery={Object.fromEntries(qs.map(q=>[q,rs?.[q]??reviewedRows(q)]))} showHeading={false}><RichNarrative id={`${PREFIX}-${id}:text`} value={text}/></ReportSection>;
 return <div className="basket-factor-appendix" id="basket-attribution-appendix">
 <section className="basket-factor-sheet basket-factor-methods">
 <N id="scope" qs={['basket_attribution_methods']} text={note['Scope narrative']}/>
 <DataComponent id={`${PREFIX}-overview`} queryId="basket_attribution_summary" title={`${note['Period label']}: all nine frozen strategies`} kind="table" displayRows={summary} sourceRows={summary}><FactorTable columns={overviewCols} rows={summary} label="All nine joint and BTC-only alpha estimates" compact/></DataComponent>
 <N id="interpretation" qs={['basket_attribution_methods','basket_attribution_summary']} text={note['Interpretation narrative']}/>
 <N id="methods" qs={['basket_attribution_methods']} text={note['Methods narrative']}/>
 </section>
 {Array.from({length:Math.ceil(summary.length/2)},(_,page)=><section className="basket-factor-sheet basket-factor-pair" key={page}>
 {summary.slice(page*2,page*2+2).map(s=>{const rr=coins.filter(c=>c.ID===s.ID);const dd=diagnostics.filter(c=>c.ID===s.ID);return <section className="basket-factor-case" key={s.ID}>
 <N id={`${s.ID}-context`} qs={['basket_attribution_summary','basket_attribution_diagnostics']} rs={{basket_attribution_summary:[s],basket_attribution_diagnostics:dd}} text={s['Case narrative']}/>
 <DataComponent id={`${PREFIX}-${s.ID}-coins`} queryId="basket_attribution_coins" title={`${s.ID}: per-coin accounting and conditional betas`} kind="table" sourceRows={rr} displayRows={rr}><FactorTable columns={cols} rows={rr} label={`${s.ID}: all eight coins`}/></DataComponent>
 </section>})}
 {page===Math.ceil(summary.length/2)-1&&<N id="companion" qs={['basket_attribution_methods','basket_attribution_coefficients']} text={note['Companion narrative']}/>}
 </section>)}
 </div>
}
