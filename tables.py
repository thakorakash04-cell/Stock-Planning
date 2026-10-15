"""Table controls shared by dashboard and full-window detail views."""
import pandas as pd
import streamlit as st
from workbook import forecast_summary

def table_controls(frame,key,selectable=False,forecast_monthly=False):
    frame=frame.copy()
    with st.expander("Filters, columns and totals",expanded=False):
        visible=st.multiselect("Visible columns — remove to hide, add to unhide",list(frame.columns),default=list(frame.columns),key=key+"_visible")
        filter_columns=st.multiselect("Filter columns",list(frame.columns),key=key+"_filtercols")
        for col in filter_columns:
            left,right=st.columns([1,2])
            numeric=pd.api.types.is_numeric_dtype(frame[col])
            options=["Contains","Equals","Choose values","Is blank","Is not blank"]+([">",">=","<","<="] if numeric else [])
            op=left.selectbox(str(col),options,key=key+"_op_"+str(col))
            series=frame[col]
            if op=="Choose values":
                values=series.dropna().drop_duplicates().tolist()
                chosen=right.multiselect("Values",values,key=key+"_values_"+str(col))
                if chosen:frame=frame[series.isin(chosen)]
            elif op=="Is blank":frame=frame[series.isna()]
            elif op=="Is not blank":frame=frame[series.notna()]
            else:
                value=right.text_input("Filter value",key=key+"_value_"+str(col))
                if value:
                    if op in (">",">=","<","<="):
                        try:
                            number=float(value.replace(",",""));numbers=pd.to_numeric(series,errors="coerce")
                            mask={">":numbers>number,">=":numbers>=number,"<":numbers<number,"<=":numbers<=number}[op]
                            frame=frame[mask]
                        except ValueError:st.warning("Enter a valid number.")
                    elif op=="Equals":frame=frame[series.astype(str).str.casefold()==value.casefold()]
                    else:frame=frame[series.astype(str).str.contains(value,case=False,regex=False,na=False)]
        numeric_cols=[c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
        sums=st.multiselect("Optional sum totals",numeric_cols,key=key+"_sums")
        if sums:st.caption("Totals use all filtered rows. Choose columns with compatible units. Production capacities sharing components are not additive.")
    if not visible:
        st.info("Choose at least one visible column above.")
        return frame,None
    search=st.text_input("Search this table",key=key+"_search",placeholder="Search any value…")
    if search:
        mask=frame.astype(str).apply(lambda s:s.str.contains(search,case=False,regex=False)).any(axis=1)
        frame=frame[mask]
    frame=frame.reset_index(drop=True)
    st.caption(f"{len(frame):,} filtered records. Use the table toolbar's full-screen control to enlarge the table.")
    height=760 if st.session_state.get("analysis_focus") else 520
    kwargs=dict(width="stretch",height=height,hide_index=True,column_order=visible,key=key+"_grid_"+str(st.session_state.get("grid_revision",0)),placeholder="—")
    if selectable:
        event=st.dataframe(frame,on_select="rerun",selection_mode="single-cell",**kwargs)
        cells=event.selection.cells
        selected=(frame.iloc[cells[0][0]].to_dict(),cells[0][1]) if cells and cells[0][0]<len(frame) else None
    else:
        st.dataframe(frame,**kwargs);selected=None
    if sums:
        totals={c:float(pd.to_numeric(frame[c],errors="coerce").sum()) for c in sums}
        if forecast_monthly and len(frame.columns)>=8:
            grouped=forecast_summary(frame)
            if frame.columns[6] in totals:totals[frame.columns[6]]=float(grouped["Current Stock"].sum())
            if frame.columns[7] in totals:totals[frame.columns[7]]=float(grouped["Pending Quantity"].sum())
        st.markdown("**Filtered totals**")
        st.table(pd.DataFrame([totals]))
    return frame,selected
