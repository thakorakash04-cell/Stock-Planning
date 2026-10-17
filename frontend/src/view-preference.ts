import {useCallback,useEffect,useRef,useState,type SetStateAction} from 'react';
import {readViewPreference,saveViewPreference} from './bridge';
export function useViewPreference<T extends object>(key:string,initial:T):[T,(value:SetStateAction<T>)=>void]{
 const read=()=>({...initial,...(readViewPreference?.(key)||{})}) as T;
 const [stored,setStored]=useState(()=>({key,value:read()}));
 const value=stored.key===key?stored.value:read();
 const current=useRef(value);current.current=value;
 useEffect(()=>{setStored({key,value:read()});const sync=()=>setStored({key,value:read()});window.addEventListener('stock-preferences-ready',sync);return()=>window.removeEventListener('stock-preferences-ready',sync)},[key]);
 const set=useCallback((update:SetStateAction<T>)=>{const next=typeof update==='function'?(update as (v:T)=>T)(current.current):update;current.current=next;setStored({key,value:next});saveViewPreference?.(key,next)},[key]);
 return [value,set];
}
