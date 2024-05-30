import streamlit as st
import pandas as pd
import os

# --- Data Persistence (Using File Storage) ---

ITEM_DATA_FILE = "item_data.xlsx"
EXCEPTION_CASES_FILE = "exception_cases.xlsx"


def load_data_if_exists(file_path, file_type):
    if os.path.exists(file_path):
        try:
            data = pd.read_excel(file_path)
            st.success(f"{file_type} file loaded from previous session.")
            return data
        except Exception as e:
            st.error(f"Error loading {file_path}: {e}")
    return None


item_data = load_data_if_exists(ITEM_DATA_FILE, "Item data")
exception_cases = load_data_if_exists(EXCEPTION_CASES_FILE, "Exception cases")

# --- File Upload Handling ---

st.title("Order Processing App")


uploaded_item_data = st.file_uploader("Upload or Re-upload Item Data File (xlsx)", type=["xlsx"])
uploaded_exception_cases = st.file_uploader("Upload or Re-upload Exception Cases File (xlsx)", type=["xlsx"])
uploaded_orders = st.file_uploader("Upload Orders File (xlsx)", type=["xlsx"])

if uploaded_orders:
    try:
        orders = pd.read_excel(uploaded_orders)
        st.success("Orders file uploaded successfully!")
    except Exception as e:
        st.error(f"Error reading orders file: {e}")

if uploaded_item_data:
    try:
        item_data = pd.read_excel(uploaded_item_data)
        item_data.to_excel(ITEM_DATA_FILE, index=False)
        st.success("Item data file uploaded and saved successfully!")
    except Exception as e:
        st.error(f"Error reading or saving item data file: {e}")

if uploaded_exception_cases:
    try:
        exception_cases = pd.read_excel(uploaded_exception_cases)
        exception_cases.to_excel(EXCEPTION_CASES_FILE, index=False)
        st.success("Exception cases file uploaded and saved successfully!")
    except Exception as e:
        st.error(f"Error reading or saving exception cases file: {e}")

# --- Data Processing (Once Reference Data Exists) ---

if item_data is not None and exception_cases is not None and 'orders' in locals():
    st.subheader("Process Orders")
    
    if st.button("Process"):
        # ---- Your Data Processing Logic ----

        # Filter out rows where `Variant SKU` starts with 'ROUTEINS' or 'KITE'
        orders = orders[~orders['Variant SKU'].astype(str).str.startswith(('ROUTEINS', 'KITE'))]

        # Create dictionaries for multipliers and name changes
        product_multipliers = dict(zip(exception_cases['Variant SKU'], exception_cases['Qty']))
        product_name_changes = dict(zip(exception_cases['Variant SKU'], exception_cases['Item Name']))

        # Apply multipliers and name changes
        orders['Quantity'] *= orders['Variant SKU'].map(product_multipliers).fillna(1)
        orders['Variant SKU'] = orders['Variant SKU'].replace(product_name_changes)

        # Aggregate and sort
        shipment = orders.groupby('Variant SKU')['Quantity'].sum().reset_index()

        # Merge data, rename and rearrange columns according to delivery note template
        delivery = (
            shipment.merge(item_data, how='left', left_on='Variant SKU', right_on='Item Name')
            .assign(Amount=lambda x:x['Quantity'] * x['Amount'])
            .assign(UOM=lambda x:x['Default Unit of Measure'])
            .rename(columns={'ID':'Item Code', 'Item Name':'Item Name', 'Variant SKU':'Description', 'Default Unit of Measure':'Stock UOM', 'Amount':'Amount (TWD)'})
            .reindex(columns=['Item Code', 'Item Name', 'Description', 'Quantity', 'Stock UOM', 'UOM', 'Amount (TWD)'])
        )

        # ---- Display & Download Results ----

        st.write("Processed orders:")
        st.write(delivery)

        st.download_button(
            label="Download Delivery as CSV",
            data=delivery.to_csv(index=False).encode('utf-8'),
            file_name='delivery.csv',
            mime='text/csv',
        )
else:
    st.info("Please upload all required files. Item data and exception cases files will be saved for future use.")
    
