import streamlit as st
import pandas as pd
import os

# --- Constants for Data Persistence ---
ITEM_DATA_FILE = "item_data.xlsx"
EXCEPTION_CASES_FILE = "exception_cases.xlsx"


# --- Core Processing Functions ---

def process_orders(orders_df, item_data_df, exception_cases_df):
    """
    Processes raw order data to generate a delivery note.
    Encapsulates the original data processing logic.
    """
    # Make a copy to avoid modifying the original DataFrame in session_state
    orders = orders_df.copy()

    # Filter out rows where `Variant SKU` starts with 'ROUTEINS' or 'KITE'
    orders = orders[
        ~orders["Variant SKU"].astype(str).str.startswith(("ROUTEINS", "KITE"))
    ]

    # Create dictionaries for multipliers and name changes
    product_multipliers = dict(
        zip(exception_cases_df["Variant SKU"], exception_cases_df["Quantity"])
    )
    product_name_changes = dict(
        zip(exception_cases_df["Variant SKU"], exception_cases_df["Item Name"])
    )

    # Convert 'Quantity' column in 'orders' to numeric type
    orders["Quantity"] = pd.to_numeric(orders["Quantity"], errors="coerce")

    # Apply multipliers and name changes
    orders["Quantity"] *= orders["Variant SKU"].map(product_multipliers).fillna(1)
    orders["Variant SKU"] = orders["Variant SKU"].replace(product_name_changes)

    # Aggregate and sort
    shipment = (
        orders.groupby("Variant SKU")["Quantity"]
        .sum()
        .reset_index()
        .rename(columns={"Variant SKU": "Variant_SKU"})
        .assign(Variant_SKU=lambda x: x["Variant_SKU"].str.split("+"))
        .explode("Variant_SKU")
    )

    # Define columns for the final delivery note
    col = [
        "item_code",
        "item_name",
        "description",
        "qty",
        "stock_uom",
        "uom",
        "amount",
    ]

    # Merge data, rename and rearrange columns
    delivery = (
        shipment.merge(
            item_data_df, how="left", left_on="Variant_SKU", right_on="Item Name"
        )
        .assign(amount=lambda x: x["Quantity"] * x["Amount"])
        .assign(uom=lambda x: x["Default Unit of Measure"])
        .rename(
            columns={
                "ID": "item_code",
                "Item Name": "item_name",
                "Variant_SKU": "description",
                "Quantity": "qty",
                "Default Unit of Measure": "stock_uom",
            }
        )
        .reindex(columns=col)
    )

    # The multi-index column creation seems specific to a certain format, keeping it as is.
    multi_cols = pd.MultiIndex.from_arrays([col, col, col])
    delivery.columns = multi_cols
    new_index = range(-4, len(delivery))
    delivery = delivery.reindex(new_index)

    return delivery


def process_inventory(stock_df, shopify_df, exception_cases_df):
    """
    Processes stock and shopify data to update inventory levels.
    Replaces the original loop with more efficient, vectorized operations.
    """
    # Make copies to avoid modifying original DataFrames
    shopify = shopify_df.copy()
    exception_cases = exception_cases_df.copy()

    # Create qty mapping for stock
    stock_qty = stock_df.groupby("Item Name")["Balance Qty"].sum()

    # --- Apply Inventory Logic ---
    # 1. Set base 'On hand' quantity from the main stock file
    shopify["On hand"] = shopify["SKU"].map(stock_qty).fillna(0)

    # 2. Apply fixed quantity overrides from exception cases.
    # These take precedence over the base stock quantity.
    exception_fixqty = exception_cases.groupby("Variant SKU")["Fix Qty"].sum()
    shopify["On hand"] = shopify["SKU"].map(exception_fixqty).fillna(shopify["On hand"])

    # 3. For bundled items, subtract the component quantities from the main bundle SKU.
    # This section is optimized to remove the explicit for-loop.
    exception_cases["Total Qty"] = (
        exception_cases["Fix Qty"] * exception_cases["Quantity"]
    )
    bundle_component_qty = exception_cases.groupby("Item Name")["Total Qty"].sum()

    # Map the quantities to subtract to the shopify DataFrame and subtract them.
    subtractions = shopify['SKU'].map(bundle_component_qty).fillna(0)
    shopify['On hand'] -= subtractions

    return shopify


# --- Streamlit App UI ---

st.title("Order and Inventory Processor")

# --- Session State Initialization ---
# Load persisted files at the start of a new session.
# Using st.session_state is better for managing data across reruns.

if "item_data" not in st.session_state:
    if os.path.exists(ITEM_DATA_FILE):
        st.session_state.item_data = pd.read_excel(ITEM_DATA_FILE)
    else:
        st.session_state.item_data = None

if "exception_cases" not in st.session_state:
    if os.path.exists(EXCEPTION_CASES_FILE):
        st.session_state.exception_cases = pd.read_excel(EXCEPTION_CASES_FILE)
    else:
        st.session_state.exception_cases = None


# --- File Upload Section ---
st.header("1. Upload Data Files")
st.info(
    "Upload new files below. 'Item Data' and 'Exception Cases' will be saved for future sessions."
)

uploaded_item_data = st.file_uploader("Upload Item Data (xlsx)", type=["xlsx"])
if uploaded_item_data:
    st.session_state.item_data = pd.read_excel(uploaded_item_data)
    st.session_state.item_data.to_excel(ITEM_DATA_FILE, index=False)
    st.success("Item Data file uploaded and saved.")

uploaded_exception_cases = st.file_uploader("Upload Exception Cases (xlsx)", type=["xlsx"])
if uploaded_exception_cases:
    st.session_state.exception_cases = pd.read_excel(uploaded_exception_cases)
    st.session_state.exception_cases.to_excel(EXCEPTION_CASES_FILE, index=False)
    st.success("Exception Cases file uploaded and saved.")

# --- Order Processing Section ---
with st.expander("2. Process Orders", expanded=True):
    uploaded_orders = st.file_uploader("Upload Orders File (xlsx)", type=["xlsx"])

    if uploaded_orders:
        try:
            orders_df = pd.read_excel(uploaded_orders)
            st.session_state.orders = orders_df
            st.success("Orders file uploaded successfully!")
        except Exception as e:
            st.error(f"Error reading orders file: {e}")

    if st.button("Process Orders"):
        if st.session_state.item_data is None or st.session_state.exception_cases is None or 'orders' not in st.session_state:
            st.warning("Please ensure 'Item Data', 'Exception Cases', and 'Orders' files are all loaded.")
        else:
            try:
                st.write("Processing orders...")
                processed_delivery = process_orders(
                    st.session_state.orders,
                    st.session_state.item_data,
                    st.session_state.exception_cases,
                )
                st.session_state.processed_delivery = processed_delivery
                st.write("✅ Processing complete. See results below.")
            except Exception as e:
                st.error(f"An error occurred during order processing: {e}")

    if "processed_delivery" in st.session_state:
        st.subheader("Processed Delivery Note")
        st.dataframe(st.session_state.processed_delivery)
        st.download_button(
            label="Download Delivery as CSV",
            data=st.session_state.processed_delivery.to_csv(index=False).encode("utf-8"),
            file_name="delivery.csv",
            mime="text/csv",
        )

# --- Inventory Processing Section ---
with st.expander("3. Process Inventory", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        uploaded_stock = st.file_uploader("Upload Stock File (xlsx)", type=["xlsx"])
        if uploaded_stock:
            try:
                st.session_state.stock = pd.read_excel(uploaded_stock)
                st.success("Stock file uploaded successfully!")
            except Exception as e:
                st.error(f"Error reading stock file: {e}")
    with col2:
        uploaded_shopify = st.file_uploader("Upload Shopify File (csv)", type=["csv"])
        if uploaded_shopify:
            try:
                st.session_state.shopify = pd.read_csv(uploaded_shopify)
                st.success("Shopify file uploaded successfully!")
            except Exception as e:
                st.error(f"Error reading Shopify file: {e}")

    if st.button("Process Inventories"):
        if st.session_state.exception_cases is None or 'stock' not in st.session_state or 'shopify' not in st.session_state:
            st.warning("Please ensure 'Exception Cases', 'Stock', and 'Shopify' files are all loaded.")
        else:
            try:
                st.write("Processing inventories...")
                processed_inventory = process_inventory(
                    st.session_state.stock,
                    st.session_state.shopify,
                    st.session_state.exception_cases,
                )
                st.session_state.processed_inventory = processed_inventory
                st.write("✅ Processing complete. See results below.")
            except Exception as e:
                st.error(f"An error occurred during inventory processing: {e}")

    if "processed_inventory" in st.session_state:
        st.subheader("Processed Shopify Inventory")
        st.dataframe(st.session_state.processed_inventory)
        st.download_button(
            label="Download Shopify as CSV",
            data=st.session_state.processed_inventory.to_csv(index=False).encode("utf-8"),
            file_name="shopify_updated.csv",
            mime="text/csv",
        )
