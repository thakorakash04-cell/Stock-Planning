import unittest
import pandas as pd
from workbook import forecast_summary,segment_map,segment_filter,related_tables

class WorkbookTests(unittest.TestCase):
    def test_stock_deducted_once_and_negative_balance_retained(self):
        frame=pd.DataFrame([["A","One",2026,"April",150,100,20,30],["A","One",2026,"May",200,50,20,130],["B","Two",2026,"April",10,20,2,-12]],columns=["Material","Name","Year","Month","Forecast","Transfer","Stock","Pending"])
        out=forecast_summary(frame)
        self.assertEqual(out.loc[0,"Pending Quantity"],180)
        self.assertEqual(out.loc[1,"Pending Quantity"],-12)
        self.assertEqual(out["Current Stock"].sum(),22)
    def test_source_names_components_and_related_rows(self):
        tables=[{"name":"Unique Material","headers":["Material","Source.Name"],"rows":[["A","Ostomy Care.XLSX"],["B","General Wound Care.xlsx"]]}, {"name":"BOM","headers":["Material","Component","Source.Name"],"rows":[["A","C","Ostomy Care.XLSX"],["B","C","General Wound Care.xlsx"]]}, {"name":"DP MRP","headers":["SKU Code","Segment"],"rows":[["A","Marketing category"]]}, {"name":"Stock Data","headers":["Material","Current Stock"],"rows":[["A",5],["C",20],["Z",2]]}]
        mapping=segment_map(tables)
        self.assertEqual(mapping["C"],{"Ostomy Care","General Wound Care"})
        self.assertNotIn("Marketing category",{s for v in mapping.values() for s in v})
        matched=related_tables(tables,"A")
        stock=next(t for t in matched if t["name"]=="Stock Data")
        self.assertEqual({r[0] for r in stock["rows"]},{"A","C"})
        self.assertEqual(related_tables(tables,"A",True),tables)
        bom=pd.DataFrame(tables[1]["rows"],columns=tables[1]["headers"])
        self.assertEqual(segment_filter(bom,mapping,"Ostomy Care")["Material"].tolist(),["A"])
