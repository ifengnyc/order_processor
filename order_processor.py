import streamlit as st
import pandas as pd
import numpy as np
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

st.title("Order Processing")


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
        # ---- Data Processing Logic ----

        # Filter out rows where `Variant SKU` starts with 'ROUTEINS' or 'KITE'
        orders = orders[~orders['Variant SKU'].astype(str).str.startswith(('ROUTEINS', 'KITE'))]

        # Create dictionaries for multipliers and name changes
        product_multipliers = dict(zip(exception_cases['Variant SKU'], exception_cases['Quantity']))
        product_name_changes = dict(zip(exception_cases['Variant SKU'], exception_cases['Item Name']))

        # Convert 'Quantity' column in 'orders' to numeric type
        orders['Quantity'] = pd.to_numeric(orders['Quantity'], errors='coerce')

        # Apply multipliers and name changes
        orders['Quantity'] *= orders['Variant SKU'].map(product_multipliers).fillna(1)
        orders['Variant SKU'] = orders['Variant SKU'].replace(product_name_changes)

        # Aggregate and sort
        shipment = (
            orders.groupby('Variant SKU')['Quantity']
            .sum()
            .reset_index()
            .rename(columns={'Variant SKU': 'Variant_SKU'})
            .assign(Variant_SKU=lambda x:x['Variant_SKU'].str.split('+'))
            .explode('Variant_SKU')
        )
        # Merge data, rename and rearrange columns according to delivery note template

        col = ['item_code', 'item_name', 'description', 'qty', 'stock_uom', 'uom', 'amount']

        delivery = (
            shipment.merge(item_data, how='left', left_on='Variant_SKU', right_on='Item Name')
            .assign(amount=lambda x:x['Quantity'] * x['Amount'])
            .assign(uom=lambda x:x['Default Unit of Measure'])
            .rename(columns={'ID':'item_code', 'Item Name':'item_name', 'Variant_SKU':'description', 'Quantity':'qty', 'Default Unit of Measure':'stock_uom'})
            .reindex(columns=col)
        )

        multi_cols = pd.MultiIndex.from_arrays([col, col, col])
        delivery.columns = multi_cols

        new_index = range(-4, len(delivery))
        delivery = delivery.reindex(new_index)

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



# --- File Upload Handiing ---

st.title('Inventory Processing')

uploaded_stock = st.file_uploader("Upload Stock File (xlsx)", type=["xlsx"])
uploaded_shopify = st.file_uploader("Upload Shopify File (csv)", type=["csv"])

if uploaded_stock:
    try:
        stock = pd.read_excel(uploaded_stock)
        st.success('Stock file uploaded successfully!')
    except Exception as e:
        st.error(f"Error reading stock file: {e}")

if uploaded_shopify:
    try:
        shopify = pd.read_csv(uploaded_shopify)
        st.success('Shopify file uploaded successfully!')
    except Exception as e:
        st.error(f"Error reading shopify file: {e}")

# --- Data Processing (Once Reference Data Exists) ---

if exception_cases is not None and 'stock' in locals() and 'shopify' in locals():
    st.subheader("Process Inventories (Exception Cases file is needed)")

    if st.button("Process"):
        # ---- Data Processing Logic ----

        # Create qty mapping for stock and exception cases
        stock_qty = stock.groupby('Item Name')['Balance Qty'].sum()
        exception_fixqty = exception_cases.groupby('Variant SKU')['Fix Qty'].sum()

        # Create a 'Total Qty' column in exception_cases
        exception_cases['Total Qty'] = exception_cases['Fix Qty'] * exception_cases['Quantity']

        # First, map stock quantities to the 'On hand' column in shopify
        shopify['On hand'] = shopify['SKU'].map(stock_qty).fillna(0)

        # Then, update 'On hand' using exception cases, prioritizing the 'Fix Qty'
        shopify['On hand'] = shopify['SKU'].map(exception_fixqty).fillna(shopify['On hand'])
        # Finally, update 'On hand' using exception cases, subtracting the 'Total Qty'

        for i in exception_cases['Item Name'].unique():
            shopify.loc[shopify['SKU'] == i, 'On hand'] -= exception_cases.loc[exception_cases['Item Name'] == i, 'Total Qty'].sum()

        # ---- Display & Download Results ----

        st.write("Processed inventories (shopify):")
        st.write(shopify)

        st.download_button(
            label="Download Shopify as CSV",
            data=shopify.to_csv(index=False).encode('utf-8'),
            mime='text/csv',
        )
else:
    st.info("Please upload all required files.")
