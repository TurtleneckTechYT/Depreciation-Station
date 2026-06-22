import streamlit as st
import pandas as pd
import plotly.express as px

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Fintech Auto-Depreciation Engine", page_icon="🚗", layout="wide")

# ==========================================
# 1. MOCK DATA (Fallback if no file is uploaded)
# ==========================================
@st.cache_data
def get_mock_data():
    data = [
        ("Mumbai", "Maruti", "Swift VXI", 2021, 25000, 650000, 575000),
        ("Mumbai", "Maruti", "Swift VXI", 2020, 40000, 620000, 490000),
        ("Mumbai", "Hyundai", "Creta SX", 2022, 15000, 1150000, 1020000),
        ("Mumbai", "Hyundai", "Creta SX", 2019, 55000, 1050000, 750000),
        ("Mumbai", "BMW", "3 Series 320i", 2020, 30000, 4200000, 2400000),
        ("Mumbai", "BMW", "3 Series 320i", 2018, 60000, 3900000, 1800000),
        ("Delhi", "Honda", "City ZX CVT", 2021, 20000, 1150000, 980000),
        ("Delhi", "Honda", "City ZX CVT", 2019, 45000, 1100000, 780000),
        ("Delhi", "Toyota", "Fortuner TRD", 2022, 18000, 4800000, 4400000),
        ("Delhi", "Toyota", "Fortuner TRD", 2020, 40000, 4200000, 3600000),
        ("Delhi", "Tata", "Nexon XZ+", 2022, 12000, 900000, 810000),
        ("Delhi", "Tata", "Nexon XZ+", 2020, 35000, 850000, 620000),
        ("Pune", "Maruti", "Baleno Zeta", 2021, 22000, 680000, 580000),
        ("Pune", "Maruti", "Baleno Zeta", 2019, 50000, 650000, 460000),
        ("Pune", "Hyundai", "i20 Asta", 2022, 10000, 950000, 860000),
        ("Pune", "Hyundai", "i20 Asta", 2020, 38000, 920000, 680000),
        ("Pune", "Mahindra", "XUV700 AX7", 2023, 5000, 2100000, 1950000),
        ("Jaipur", "Honda", "Amaze VX CVT", 2021, 28000, 820000, 620000),
        ("Jaipur", "Honda", "Amaze VX CVT", 2019, 52000, 790000, 490000),
        ("Jaipur", "Maruti", "Ertiga VXI", 2020, 42000, 950000, 650000),
        ("Jaipur", "Audi", "A4 Technology", 2019, 48000, 4200000, 1950000),
        ("Jaipur", "Audi", "A4 Technology", 2017, 75000, 4000000, 1450000),
        ("Chennai", "Toyota", "Innova Crysta ZX", 2021, 30000, 2100000, 1850000),
        ("Chennai", "Toyota", "Innova Crysta ZX", 2018, 65000, 1950000, 1450000),
        ("Chennai", "Kia", "Seltos HTX", 2022, 14000, 1200000, 1050000),
        ("Chennai", "Kia", "Seltos HTX", 2020, 40000, 1150000, 820000),
    ]
    return pd.DataFrame(data, columns=["City", "Brand", "Model", "Year", "KMs_Driven", "Original_MSRP", "Used_Price"])

# ==========================================
# 2. DATA PROCESSING ENGINE
# ==========================================
def process_depreciation(df):
    current_year = 2024
    df['Age'] = current_year - df['Year']
    df['Depreciation_Rate_%'] = ((df['Original_MSRP'] - df['Used_Price']) / df['Original_MSRP']) * 100
    df['Annualized_Depreciation_%'] = df['Depreciation_Rate_%'] / df['Age']
    # Drop rows with missing critical data
    df = df.dropna(subset=['Depreciation_Rate_%'])
    return df

# ==========================================
# 3. USER INTERFACE (THE WEBPAGE)
# ==========================================

st.title("🚗 Indian Auto-Depreciation & Loan Risk Engine")
st.markdown("Built for Fintech Auto-Loan Underwriting & Collateral Valuation")

# --- SIDEBAR: DATA UPLOAD ---
with st.sidebar:
    st.header("📁 Data Source")
    st.write("Upload your own scraped CSV, or use the built-in mock data.")
    
    uploaded_file = st.file_uploader("Upload CSV (OLX/CarWale format)", type=['csv'])
    
    st.caption("⚠️ **Required CSV Columns:** `City`, `Brand`, `Model`, `Year`, `KMs_Driven`, `Original_MSRP`, `Used_Price`")
    use_mock = st.checkbox("Use Mock Data Instead", value=True)

# --- LOAD DATA ---
if uploaded_file is not None:
    try:
        raw_df = pd.read_csv(uploaded_file)
        # Standardize column names just in case (e.g., 'city' vs 'City')
        raw_df.columns = [col.strip().title() for col in raw_df.columns]
        df = process_depreciation(raw_df)
        st.success(f"✅ Successfully loaded and processed {len(df)} records from your CSV!")
    except Exception as e:
        st.error(f"Error reading CSV. Check column names. Error: {e}")
        df = None
elif use_mock:
    df = process_depreciation(get_mock_data())
    st.info("Using built-in Indian Market Mock Data (Mumbai, Delhi, Pune, Jaipur, Chennai).")
else:
    st.warning("Please upload a CSV or check 'Use Mock Data'.")
    df = None

# --- IF DATA EXISTS, BUILD DASHBOARD ---
if df is not None and not df.empty:

    # KPI METRICS ROW
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Vehicles Analyzed", len(df))
    col2.metric("Avg Market Depreciation", f"{df['Depreciation_Rate_%'].mean():.1f}%")
    col3.metric("Cities Covered", df['City'].nunique())
    col4.metric("Brands Covered", df['Brand'].nunique())

    st.markdown("---")
    
    # CHARTS ROW
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📉 Depreciation by City (Collateral Risk)")
        city_risk = df.groupby('City')['Depreciation_Rate_%'].mean().reset_index()
        fig_city = px.bar(city_risk, x='City', y='Depreciation_Rate_%', color='Depreciation_Rate_%',
                          color_continuous_scale="RdYlGn_r", title="Higher % = Higher Risk for Lenders")
        st.plotly_chart(fig_city, use_container_width=True)

    with col_right:
        st.subheader("📊 Brand Value Retention")
        brand_risk = df.groupby('Brand')['Depreciation_Rate_%'].mean().reset_index().sort_values('Depreciation_Rate_%')
        fig_brand = px.bar(brand_risk, y='Brand', x='Depreciation_Rate_%', orientation='h',
                           color='Depreciation_Rate_%', color_continuous_scale="Viridis")
        st.plotly_chart(fig_brand, use_container_width=True)

    st.markdown("---")

    # INTERACTIVE UNDERWRITING TOOL
    st.subheader("🔧 Interactive Loan Underwriting Simulator")
    st.write("Simulate an NBFC loan approval. Does the vehicle hold enough value to secure the requested loan amount? (Max LTV = 80%)")
    
    tool_col1, tool_col2, tool_col3 = st.columns(3)
    
    with tool_col1:
        selected_city = st.selectbox("Select City", options=df['City'].unique())
    with tool_col2:
        selected_brand = st.selectbox("Select Brand", options=df['Brand'].unique())
    with tool_col3:
        requested_loan = st.number_input("Requested Loan Amount (₹)", min_value=0, max_value=100000000, value=500000, step=50000)

    calculate_btn = st.button("Calculate Risk", type="primary")

    if calculate_btn:
        # Filter data for the selected parameters
        similar_cars = df[(df['City'] == selected_city) & (df['Brand'] == selected_brand)]
        
        if similar_cars.empty:
            st.error("No data available for this combination.")
        else:
            expected_dep = similar_cars['Depreciation_Rate_%'].mean()
            # Assume the collateral is roughly the average used price of that brand in that city
            estimated_collateral = similar_cars['Used_Price'].mean() 
            max_safe_loan = estimated_collateral * 0.80 # 80% LTV standard in India
            
            st.markdown("### 📑 Underwriting Report")
            report_col1, report_col2 = st.columns(2)
            
            with report_col1:
                st.info(f"**Expected Depreciation:** {expected_dep:.1f}%\n\n**Estimated Collateral Value:** ₹{estimated_collateral:,.0f}")
            
            with report_col2:
                if requested_loan <= max_safe_loan:
                    st.success(f"**✅ APPROVE**\n\nMax Safe Loan (80% LTV): ₹{max_safe_loan:,.0f}\nRequested Loan: ₹{requested_loan:,.0f}")
                else:
                    st.error(f"**🚨 REJECT**\n\nMax Safe Loan (80% LTV): ₹{max_safe_loan:,.0f}\nRequested Loan: ₹{requested_loan:,.0f}\n\n*Loan exceeds safe collateral limits.*")
