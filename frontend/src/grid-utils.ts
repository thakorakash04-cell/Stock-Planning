export type Cell=string|number|null;
export type ColumnFilter={op?:string;text?:string;values?:string[]};
export const cellKey=(v:Cell)=>JSON.stringify(v);
export function filterRows(rows:Cell[][],filters:Record<string,ColumnFilter>,headers:string[]){return rows.filter(r=>headers.every((h,i)=>{const f=filters[h];if(!f)return true;const v=r[i]??null;if(f.values?.length&&!f.values.includes(cellKey(v)))return false;if(!f.text)return true;const text=f.text.toLowerCase(),str=String(v??'').toLowerCase();switch(f.op){case 'eq':return str===text;case 'neq':return str!==text;case 'gt':case 'gte':case 'lt':case 'lte':{const x=typeof v==='number'?v:NaN,y=Number(f.text.replaceAll(',',''));return Number.isFinite(x)&&Number.isFinite(y)&&(f.op==='gt'?x>y:f.op==='gte'?x>=y:f.op==='lt'?x<y:x<=y)}default:return str.includes(text)}}))}
export function sumColumn(rows:Cell[][],i:number){return rows.reduce((sum,r)=>sum+(typeof r[i]==='number'&&Number.isFinite(r[i])?r[i] as number:0),0)}
