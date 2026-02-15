
import frappe
import json
from typing import Dict, List, Any

class SystemMapper:
    """
    Builds a Knowledge Graph of Frappe DocTypes and their relationships.
    Identifies:
    - DocType Hierarchy
    - Link Field Relationships
    - Child Table Relationships
    - Module Grouping
    """
    
    def __init__(self):
        self.graph = {
            "doctypes": {},
            "links": [],
            "modules": {}
        }

    def map_system(self):
        """Scan all DocTypes and build relationship map."""
        # Get custom DocTypes OR DocTypes from Growth System related modules
        nbfc_modules = ["LOS", "LMS", "Co-Lending", "Accounting", "Litigation", "HR"]
        
        doctypes = frappe.get_all("DocType", filters=[
            ["istable", "=", 0],
            ["issingle", "=", 0],
            ["module", "in", nbfc_modules + ["Custom"]]
        ])
        
        for dt in doctypes:
            name = dt.name
            meta = frappe.get_meta(name)
            
            # Module grouping
            module = meta.module
            if module not in self.graph["modules"]:
                self.graph["modules"][module] = []
            self.graph["modules"][module].append(name)
            
            # DocType metadata
            self.graph["doctypes"][name] = {
                "label": meta.name,
                "module": module,
                "fields": [],
                "links": [],
                "child_tables": []
            }
            
            # Analyze fields
            for field in meta.fields:
                field_info = {
                    "fieldname": field.fieldname,
                    "label": field.label,
                    "fieldtype": field.fieldtype
                }
                self.graph["doctypes"][name]["fields"].append(field_info)
                
                # Check for Links
                if field.fieldtype == "Link" and field.options:
                    self.graph["doctypes"][name]["links"].append({
                        "field": field.fieldname,
                        "target": field.options
                    })
                    self.graph["links"].append({
                        "source": name,
                        "target": field.options,
                        "type": "link",
                        "field": field.fieldname
                    })
                
                # Check for Child Tables
                if field.fieldtype in ["Table", "Table MultiSelect"] and field.options:
                    self.graph["doctypes"][name]["child_tables"].append(field.options)
                    self.graph["links"].append({
                        "source": name,
                        "target": field.options,
                        "type": "child_table",
                        "field": field.fieldname
                    })

        # Save to cache
        frappe.cache().set_value("niv_system_knowledge_graph", json.dumps(self.graph))
        return self.graph

    def get_visualization_data(self):
        """Format data for Cytoscape.js visualizer."""
        graph = self.map_system()
        elements = []
        node_ids = set()
        
        # Add Nodes (DocTypes)
        for name, info in graph["doctypes"].items():
            elements.append({
                "data": {
                    "id": name,
                    "label": info["label"],
                    "module": info["module"],
                    "type": "doctype"
                }
            })
            node_ids.add(name)
            
        # Add Edges (Only if both source and target nodes exist)
        for link in graph["links"]:
            if link['source'] in node_ids and link['target'] in node_ids:
                elements.append({
                    "data": {
                        "id": f"{link['source']}-{link['target']}-{link['field']}",
                        "source": link["source"],
                        "target": link["target"],
                        "label": link["field"],
                        "type": link["type"]
                    }
                })
            
        return elements

def get_graph_elements():
    mapper = SystemMapper()
    return mapper.get_visualization_data()

def update_knowledge_graph():
    mapper = SystemMapper()
    graph = mapper.map_system()
    return graph
