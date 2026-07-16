import streamlit as st
import pandas as pd
import io
import requests
from bs4 import BeautifulSoup
from google.cloud import firestore
from google.oauth2 import service_account

st.set_page_config(page_title="مدیریت هوشمند خرید (Firestore)", layout="wide")

# ================= تنظیمات دیتابیس Firestore =================
@st.cache_resource
def get_db():
    try:
        # خواندن کلید امنیتی از Secrets استریم‌لیت
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(credentials=creds, project_id=creds_dict["project_id"])
        return db
    except Exception as e:
        st.error(f"خطا در اتصال به دیتابیس Firestore. آیا کدهای امنیتی را در Secrets قرار داده‌اید؟ \n {e}")
        st.stop()

def init_db():
    db = get_db()
    # بررسی و ساخت داک تنظیمات در صورت عدم وجود
    config_ref = db.collection("settings").document("global_config")
    doc = config_ref.get()
    if not doc.exists:
        config_ref.set({
            "yuan_rate": 9000.0,
            "lifetime_yuan": 0.0,
            "lifetime_shipping": 0.0,
            "lifetime_net_sales": 0.0
        })

def get_settings():
    db = get_db()
    doc = db.collection("settings").document("global_config").get()
    if doc.exists:
        return doc.to_dict()
    return {"yuan_rate": 9000.0, "lifetime_yuan": 0.0, "lifetime_shipping": 0.0, "lifetime_net_sales": 0.0}

def save_settings(settings_dict):
    db = get_db()
    db.collection("settings").document("global_config").set(settings_dict)

def get_products():
    db = get_db()
    docs = db.collection("products").stream()
    records = [doc.to_dict() for doc in docs]
    
    headers = ["id", "name", "category", "status", "supplier_link", "digikala_link", "dkp_code", 
               "quantity_needed", "length_cm", "width_cm", "height_cm", "pcs_per_carton", 
               "cbm_rate_toman", "buy_price_yuan", "digikala_price_toman", "tax_amount_toman", 
               "commission_percent", "processing_fee_toman", "pure_profit_toman", "profit_percent", 
               "carton_weight_kg", "net_sales_toman"]
               
    if not records:
        df = pd.DataFrame(columns=headers)
    else:
        df = pd.DataFrame(records)
        for h in headers:
            if h not in df.columns:
                df[h] = ""
    
    num_cols = ["quantity_needed", "length_cm", "width_cm", "height_cm", "pcs_per_carton", 
                "cbm_rate_toman", "buy_price_yuan", "digikala_price_toman", "tax_amount_toman", 
                "commission_percent", "processing_fee_toman", "pure_profit_toman", "profit_percent", 
                "carton_weight_kg", "net_sales_toman"]
                
    str_cols = ["name", "category", "status", "supplier_link", "digikala_link", "dkp_code"]
    
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype('float64')
        
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
            
    return df

def save_products(df):
    db = get_db()
    col_ref = db.collection("products")
    
    # دریافت لیست مستندات موجود جهت همگام‌سازی و حذف مواردی که دیلیت شده‌اند
    docs = col_ref.stream()
    existing_ids = {doc.id for doc in docs}
    df_ids = {str(int(float(x))) for x in df['id'].tolist() if pd.notna(x)}
    
    # عملیات دسته‌ای (Batch) برای سرعت بی‌نظیر و عدم قطعی
    batch = db.batch()
    
    # حذف ردیف‌های حذف شده
    for doc_id in (existing_ids - df_ids):
        batch.delete(col_ref.document(doc_id))
        
    # ثبت و آپدیت ردیف‌های موجود
    for _, row in df.iterrows():
        doc_id = str(int(float(row['id'])))
        doc_ref = col_ref.document(doc_id)
        row_dict = row.fillna("").to_dict()
        
        # تبدیل انواع داده‌های numpy به پایتون بومی جهت همخوانی با فایربیس
        clean_dict = {}
        for k, v in row_dict.items():
            if hasattr(v, 'item'):
                clean_dict[k] = v.item()
            else:
                clean_dict[k] = v
        batch.set(doc_ref, clean_dict)
        
    batch.commit()

STATUS_OPTIONS = ["کالاهای درخواستی", "کالاهای خریداری شده (انبار چین)", "کالاهای ارسال شده", "کالاهای موجود"]
ACTIVE_STATUSES = ["کالاهای خریداری شده (انبار چین)", "کالاهای ارسال شده", "کالاهای موجود"]

# ================= سیستم ورود (Login) =================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.title("🔐 ورود به سیستم")
    with st.form("login_form"):
        username = st.text_input("نام کاربری")
        password = st.text_input("رمز عبور", type="password")
        submit = st.form_submit_button("ورود")
        if submit:
            if username == "Admin" and password == "Sw.123456":
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("نام کاربری یا رمز عبور اشتباه است.")
    st.stop()

# راه‌اندازی پایگاه داده در سشن اول
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

settings_data = get_settings()
saved_yuan = settings_data.get('yuan_rate', 9000.0)

def get_live_yuan():
    try:
        res = requests.get('https://brsapi.ir/FreeTsetmcBourseApi/Api_Free_Gold_Currency_v2.json', timeout=5)
        if res.status_code == 200:
            data = res.json()
            if 'currency' in data:
                for item in data['currency']:
                    if 'یوان' in item.get('name', ''):
                        return int(item['price'] / 10) 
    except:
        pass
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        res = requests.get('https://www.tgju.org/profile/price_cny', headers=headers, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_tag = soup.find('span', {'data-col': 'info.last_trade.PDrCotVal'})
        if price_tag:
            price_rial = int(price_tag.text.replace(',', ''))
            return int(price_rial / 10)
    except:
        pass
    return None

with st.sidebar:
    st.header("تنظیمات عمومی")
    
    if st.button("🔄 آپدیت آنلاین قیمت یوان"):
        live_price = get_live_yuan()
        if live_price:
            settings_data['yuan_rate'] = float(live_price)
            save_settings(settings_data)
            st.success(f"آپدیت شد: {live_price:,} تومان")
            st.rerun()
        else:
            st.error("خطا در دریافت قیمت. سایت مبدا پاسخگو نیست.")

    yuan_rate = st.number_input("نرخ روز یوان (تومان):", value=int(saved_yuan), step=100)
    if st.button("💾 ذخیره قیمت دستی"):
        settings_data['yuan_rate'] = float(yuan_rate)
        save_settings(settings_data)
        st.success("قیمت جدید ثبت شد!")
        st.rerun()

    st.markdown("---")
    st.subheader("تنظیمات آمار")
    if st.button("⚠️ صفر کردن کنتور انباشتی خرید"):
        settings_data['lifetime_yuan'] = 0.0
        settings_data['lifetime_shipping'] = 0.0
        settings_data['lifetime_net_sales'] = 0.0
        save_settings(settings_data)
        st.success("آمار کنتور صفر شد!")
        st.rerun()


# ================= توابع محاسباتی =================
def calculate_fees(dk_price, comm_pct):
    if dk_price <= 0:
        return 0.0, 0.0
    proc_fee = dk_price * 0.07
    proc_fee = max(36000.0, min(proc_fee, 240000.0))
    comm_amount = dk_price * (comm_pct / 100.0)
    tax = (0.10 * (proc_fee / 2.0)) + (0.10 * comm_amount)
    return float(proc_fee), float(tax)

def dynamic_calc(row, current_yuan):
    try:
        length = float(row['length_cm'])
        width = float(row['width_cm'])
        height = float(row['height_cm'])
        pcs = int(row['pcs_per_carton'])
        qty = int(row['quantity_needed'])
        cbm_rate = float(row['cbm_rate_toman'])
        price_yuan = float(row['buy_price_yuan'])
        dk_price = float(row['digikala_price_toman'])
        comm_pct = float(row['commission_percent'])
        
        proc_fee, tax = calculate_fees(dk_price, comm_pct)
        
        carton_cbm = (length * width * height) / 1000000
        item_cbm = carton_cbm / pcs if pcs > 0 else 0
        item_shipping_toman = item_cbm * cbm_rate
        item_cost_toman = (price_yuan * current_yuan) + item_shipping_toman
        
        comm_amount = dk_price * (comm_pct / 100.0)
        item_dk_net = dk_price - tax - comm_amount - proc_fee
        
        item_profit = item_dk_net - item_cost_toman
        total_net_profit = item_profit * qty
        
        profit_margin_pct = (item_profit / dk_price) * 100 if dk_price > 0 else 0
        
        return pd.Series([total_net_profit, profit_margin_pct, item_dk_net, proc_fee, tax, item_shipping_toman])
    except Exception as e:
        return pd.Series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

def render_product_table(df_subset, tab_key):
    if df_subset.empty:
        st.info("لیست کالاها در این بخش خالی است.")
        return
        
    st.info("💡 برای ویرایش اطلاعات، روی سلول‌ها کلیک کنید. ارزش افزوده، هزینه پردازش و هزینه حمل خودکار محاسبه می‌شوند.")
    
    display_df = df_subset.copy()
    display_df['cbm_rate_toman'] = display_df['cbm_rate_toman'].map('{:,.0f}'.format)
    display_df['digikala_price_toman'] = display_df['digikala_price_toman'].map('{:,.0f}'.format)
    display_df['tax_amount_toman'] = display_df['tax_amount_toman'].map('{:,.0f}'.format)
    display_df['processing_fee_toman'] = display_df['processing_fee_toman'].map('{:,.0f}'.format)
    display_df['item_shipping_toman'] = display_df['item_shipping_toman'].map('{:,.0f}'.format)
    display_df['net_sales_toman'] = display_df['net_sales_toman'].map('{:,.0f}'.format)
    display_df['pure_profit_toman'] = display_df['pure_profit_toman'].map('{:,.0f}'.format)
    display_df['profit_percent'] = display_df['profit_percent'].map('{:.2f} %'.format)
    display_df['cbm_per_carton'] = display_df['cbm_per_carton'].map('{:.4f}'.format)

    edited_df = st.data_editor(
        display_df,
        key=f"editor_{tab_key}",
        use_container_width=True,
        hide_index=True,
        column_order=[
            "id", "name", "category", "status", "dkp_code", "quantity_needed",
            "pcs_per_carton", "cbm_per_carton", "cbm_rate_toman", "item_shipping_toman", "buy_price_yuan",
            "digikala_price_toman", "commission_percent", "processing_fee_toman", "tax_amount_toman",
            "net_sales_toman", "pure_profit_toman", "profit_percent"
        ],
        column_config={
            "id": st.column_config.NumberColumn("شناسه", disabled=True),
            "name": "نام کالا",
            "category": "دسته بندی",
            "status": st.column_config.SelectboxColumn("وضعیت", options=STATUS_OPTIONS),
            "supplier_link": st.column_config.LinkColumn("لینک تامین", display_text="🔗 سایت"),
            "digikala_link": st.column_config.LinkColumn("لینک دیجی", display_text="🔗 سایت"),
            "dkp_code": "کد DKP",
            "quantity_needed": st.column_config.NumberColumn("تعداد نیاز"),
            "length_cm": st.column_config.NumberColumn("طول (cm)"),
            "width_cm": st.column_config.NumberColumn("عرض (cm)"),
            "height_cm": st.column_config.NumberColumn("ارتفاع (cm)"),
            "carton_weight_kg": st.column_config.NumberColumn("وزن هر کارتن (kg)"),
            "pcs_per_carton": st.column_config.NumberColumn("تعداد در کارتن"),
            "cbm_rate_toman": st.column_config.TextColumn("هزینه CBM (تومان)"),
            "item_shipping_toman": st.column_config.TextColumn("هزینه حمل واحد", disabled=True),
            "buy_price_yuan": st.column_config.NumberColumn("قیمت خرید(یوان)"),
            "digikala_price_toman": st.column_config.TextColumn("قیمت فروش (تومان)"),
            "tax_amount_toman": st.column_config.TextColumn("ارزش افزوده", disabled=True),
            "commission_percent": st.column_config.NumberColumn("کمیسیون (%)"),
            "processing_fee_toman": st.column_config.TextColumn("هزینه پردازش", disabled=True),
            "net_sales_toman": st.column_config.TextColumn("خالص فروش هر واحد", disabled=True),
            "pure_profit_toman": st.column_config.TextColumn("سود خالص کل (تومان)", disabled=True),
            "profit_percent": st.column_config.TextColumn("حاشیه سود", disabled=True),
            "cbm_per_carton": st.column_config.TextColumn("CBM هر کارتن", disabled=True),
        }
    )

    lt_settings = get_settings()
    lt_yuan = lt_settings.get('lifetime_yuan', 0.0)
    lt_shipping = lt_settings.get('lifetime_shipping', 0.0)
    lt_net_sales = lt_settings.get('lifetime_net_sales', 0.0)

    st.markdown(f"""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 2px solid #198754; margin-top: 15px; margin-bottom: 20px; display: flex; justify-content: space-around; flex-wrap: wrap; gap: 15px;'>
        <div style='text-align: center; flex: 1; min-width: 200px;'>
            <p style='margin: 0; color: #6c757d; font-size: 14px; font-weight: bold;'>مجموع خریدهای انباشتی (یوان)</p>
            <h2 style='margin: 5px 0 0 0; color: #0d6efd;'>{lt_yuan:,.0f} ¥</h2>
        </div>
        <div style='text-align: center; flex: 1; min-width: 200px;'>
            <p style='margin: 0; color: #6c757d; font-size: 14px; font-weight: bold;'>مجموع هزینه‌های حمل (تومان)</p>
            <h2 style='margin: 5px 0 0 0; color: #dc3545;'>{lt_shipping:,.0f} ₮</h2>
        </div>
        <div style='text-align: center; flex: 1; min-width: 200px;'>
            <p style='margin: 0; color: #6c757d; font-size: 14px; font-weight: bold;'>مبلغ خالص فروش کل (تومان)</p>
            <h2 style='margin: 5px 0 0 0; color: #198754;'>{lt_net_sales:,.0f} ₮</h2>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("💾 ذخیره تغییرات", key=f"save_btn_{tab_key}"):
        df_all = get_products()
        df_all = df_all.astype(object)
        
        added_lt_yuan = 0.0
        added_lt_shipping = 0.0
        added_lt_net_sales = 0.0

        for _, row in edited_df.iterrows():
            orig_row = df_subset[df_subset['id'] == row['id']].iloc[0]
            
            cbm_clean = float(str(row['cbm_rate_toman']).replace(',', ''))
            dk_clean = float(str(row['digikala_price_toman']).replace(',', ''))
            comm_val = float(row['commission_percent'])
            
            proc_calc, tax_calc = calculate_fees(dk_clean, comm_val)
            
            if orig_row['status'] not in ACTIVE_STATUSES and row['status'] in ACTIVE_STATUSES:
                added_lt_yuan += float(row['buy_price_yuan'] * row['quantity_needed'])
                cbm = (row['length_cm'] * row['width_cm'] * row['height_cm']) / 1000000
                pcs = row['pcs_per_carton'] if row['pcs_per_carton'] > 0 else 1
                added_lt_shipping += float((cbm / pcs) * cbm_clean * row['quantity_needed'])
                
                dk_net_single = dk_clean - tax_calc - (dk_clean * (comm_val / 100)) - proc_calc
                added_lt_net_sales += float(dk_net_single * row['quantity_needed'])

            idx = df_all.index[df_all['id'] == row['id']].tolist()
            if idx:
                i = idx[0]
                df_all.loc[i, 'name'] = str(row['name'])
                df_all.loc[i, 'category'] = str(row['category'])
                df_all.loc[i, 'status'] = str(row['status'])
                df_all.loc[i, 'supplier_link'] = str(row['supplier_link'])
                df_all.loc[i, 'digikala_link'] = str(row['digikala_link'])
                df_all.loc[i, 'dkp_code'] = str(row['dkp_code'])
                df_all.loc[i, 'quantity_needed'] = float(row['quantity_needed'])
                df_all.loc[i, 'length_cm'] = float(row['length_cm'])
                df_all.loc[i, 'width_cm'] = float(row['width_cm'])
                df_all.loc[i, 'height_cm'] = float(row['height_cm'])
                df_all.loc[i, 'pcs_per_carton'] = float(row['pcs_per_carton'])
                df_all.loc[i, 'cbm_rate_toman'] = float(cbm_clean)
                df_all.loc[i, 'buy_price_yuan'] = float(row['buy_price_yuan'])
                df_all.loc[i, 'digikala_price_toman'] = float(dk_clean)
                df_all.loc[i, 'tax_amount_toman'] = float(tax_calc)
                df_all.loc[i, 'commission_percent'] = float(comm_val)
                df_all.loc[i, 'processing_fee_toman'] = float(proc_calc)
                df_all.loc[i, 'carton_weight_kg'] = float(row['carton_weight_kg'])
            
        save_products(df_all)
        
        if added_lt_yuan > 0 or added_lt_shipping > 0 or added_lt_net_sales > 0:
            lt_settings = get_settings()
            lt_settings['lifetime_yuan'] = lt_settings.get('lifetime_yuan', 0.0) + added_lt_yuan
            lt_settings['lifetime_shipping'] = lt_settings.get('lifetime_shipping', 0.0) + added_lt_shipping
            lt_settings['lifetime_net_sales'] = lt_settings.get('lifetime_net_sales', 0.0) + added_lt_net_sales
            save_settings(lt_settings)
            
        st.success("تغییرات با موفقیت ذخیره شد!")
        st.rerun()

    st.markdown("---")
    with st.expander("🗑️ حذف کالا از سیستم"):
        col1, col2 = st.columns([3, 1])
        options = {f"{row['id']} - {row['name']}": row['id'] for _, row in df_subset.iterrows()}
        if options:
            selected_to_delete = col1.selectbox("کالای مورد نظر را برای حذف انتخاب کنید:", list(options.keys()), key=f"del_sel_{tab_key}")
            if col2.button("حذف دائمی", key=f"del_btn_{tab_key}"):
                prod_id = options[selected_to_delete]
                df_all = get_products()
                df_all = df_all[df_all['id'] != prod_id]
                save_products(df_all)
                st.success("کالا با موفقیت حذف شد!")
                st.rerun()

# ================= خواندن اطلاعات و تب‌ها =================
df = get_products()

# اعمال محاسبات پویا در صورت عدم خالی بودن دیتابیس
if not df.empty:
    df[['pure_profit_toman', 'profit_percent', 'net_sales_toman', 'processing_fee_toman', 'tax_amount_toman', 'item_shipping_toman']] = df.apply(lambda r: dynamic_calc(r, yuan_rate), axis=1, result_type='expand')
    df['cbm_per_carton'] = (pd.to_numeric(df['length_cm']) * pd.to_numeric(df['width_cm']) * pd.to_numeric(df['height_cm'])) / 1000000
    
    # سایدبار گزارش زنده
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 گزارش مالی (زنده)")
    for status in STATUS_OPTIONS:
        df_status = df[df['status'] == status]
        total_yuan = (pd.to_numeric(df_status['buy_price_yuan']) * pd.to_numeric(df_status['quantity_needed'])).sum() if not df_status.empty else 0
        total_profit = pd.to_numeric(df_status['pure_profit_toman']).sum() if not df_status.empty else 0
        total_net_sales = (pd.to_numeric(df_status['net_sales_toman']) * pd.to_numeric(df_status['quantity_needed'])).sum() if not df_status.empty else 0
        
        st.sidebar.markdown(f"**{status}**")
        st.sidebar.caption(f"🔹 ارزش: `{total_yuan:,.0f}` یوان")
        st.sidebar.caption(f"🟩 کل خالص فروش: `{total_net_sales:,.0f}` تومان")
        st.sidebar.caption(f"🔸 سود خالص: `{total_profit:,.0f}` تومان")

# بخش سرچ کالا (سراسری)
st.subheader("🔍 جستجوی هوشمند")
search_query = st.text_input("نام کالا یا کد DKP را وارد کنید:", key="global_search_input")

# فیلتر کردن دیتافریم بر اساس سرچ کاربر
df_filtered = df
if search_query:
    df_filtered = df[df['name'].str.contains(search_query, case=False, na=False) | 
                     df['dkp_code'].astype(str).str.contains(search_query, case=False, na=False)]

tabs = st.tabs(["📋 کل کالاها", "🛒 درخواستی", "🇨🇳 انبار چین", "✈️ ارسال شده", "📦 موجود", "➕ افزودن جدید", "💡 پیشنهاد خرید", "📥 اکسل"])

with tabs[0]: 
    render_product_table(df_filtered, "all")
with tabs[1]: 
    render_product_table(df_filtered[df_filtered['status'] == 'کالاهای درخواستی'], "req")
with tabs[2]: 
    render_product_table(df_filtered[df_filtered['status'] == 'کالاهای خریداری شده (انبار چین)'], "china")
with tabs[3]: 
    render_product_table(df_filtered[df_filtered['status'] == 'کالاهای ارسال شده'], "sent")
with tabs[4]: 
    render_product_table(df_filtered[df_filtered['status'] == 'کالاهای موجود'], "stock")

with tabs[5]:
    with st.form("add_product_form"):
        col1, col2, col3 = st.columns(3)
        name = col1.text_input("نام کالا")
        category = col2.text_input("دسته بندی")
        status = col3.selectbox("وضعیت خرید", STATUS_OPTIONS)
        
        col4, col5, col6 = st.columns(3)
        sup_link = col4.text_input("لینک تامین کننده")
        dk_link = col5.text_input("لینک دیجی کالا")
        dkp = col6.text_input("کد DKP")
        
        col7, col8, col9, col10 = st.columns(4)
        qty = col7.number_input("تعداد نیاز", min_value=1, value=10)
        buy_price = col8.number_input("قیمت خرید (یوان)", min_value=0.0, value=10.0)
        pcs_carton = col9.number_input("تعداد در کارتن", min_value=1, value=50)
        cbm_rate = col10.number_input("هزینه هر CBM (تومان)", min_value=0.0, value=15000000.0)
        
        col11, col12, col13, col_weight = st.columns(4)
        length = col11.number_input("طول (cm)", min_value=0.0, value=50.0)
        width = col12.number_input("عرض (cm)", min_value=0.0, value=40.0)
        height = col13.number_input("ارتفاع (cm)", min_value=0.0, value=30.0)
        weight = col_weight.number_input("وزن کارتن (kg)", min_value=0.0, value=10.0)
        
        col14, col15 = st.columns(2)
        dk_price = col14.number_input("قیمت فروش (تومان)", min_value=0.0, value=200000.0)
        comm = col15.number_input("کمیسیون (%)", min_value=0.0, value=5.0)
        
        if st.form_submit_button("ثبت کالا"):
            df_all = get_products()
            
            # محاسبه مطمئن شناسه جدید
            current_max_id = 0
            if not df_all.empty and 'id' in df_all.columns:
                valid_ids = pd.to_numeric(df_all['id'], errors='coerce').dropna()
                if not valid_ids.empty:
                    current_max_id = int(valid_ids.max())
            new_id = current_max_id + 1
            
            proc_calc, tax_calc = calculate_fees(dk_price, comm)
            
            new_row = {
                'id': new_id, 'name': name, 'category': category, 'status': status, 
                'supplier_link': sup_link, 'digikala_link': dk_link, 'dkp_code': dkp, 
                'quantity_needed': float(qty), 'length_cm': float(length), 'width_cm': float(width), 'height_cm': float(height), 
                'pcs_per_carton': float(pcs_carton), 'cbm_rate_toman': float(cbm_rate), 'buy_price_yuan': float(buy_price), 
                'digikala_price_toman': float(dk_price), 'tax_amount_toman': float(tax_calc), 'commission_percent': float(comm), 
                'processing_fee_toman': float(proc_calc), 'pure_profit_toman': 0.0, 'profit_percent': 0.0, 
                'carton_weight_kg': float(weight), 'net_sales_toman': 0.0
            }
            
            df_all = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
            save_products(df_all)
            
            if status in ACTIVE_STATUSES:
                added_yuan = buy_price * qty
                cbm = (length * width * height) / 1000000
                pcs = pcs_carton if pcs_carton > 0 else 1
                added_shipping = (cbm / pcs) * cbm_rate * qty
                added_net_sales = (dk_price - tax_calc - (dk_price * (comm / 100)) - proc_calc) * qty
                
                lt_settings = get_settings()
                lt_settings['lifetime_yuan'] = lt_settings.get('lifetime_yuan', 0.0) + added_yuan
                lt_settings['lifetime_shipping'] = lt_settings.get('lifetime_shipping', 0.0) + added_shipping
                lt_settings['lifetime_net_sales'] = lt_settings.get('lifetime_net_sales', 0.0) + added_net_sales
                save_settings(lt_settings)
                
            st.success("کالا ثبت شد!")
            st.rerun()

with tabs[6]:
    st.subheader("💡 تخصیص هوشمند بودجه (مخصوص کالاهای درخواستی)")
    budget = st.number_input("بودجه (یوان):", min_value=0, value=30000, step=1000)
    
    if not df.empty:
        df_budget = df[df['status'] == 'کالاهای درخواستی'].copy()
        if not df_budget.empty:
            # مرتب‌سازی بر اساس حاشیه سود نزولی
            df_budget = df_budget.sort_values(by='profit_percent', ascending=False)
            
            suggested = []
            rem_budget = budget
            
            for _, p in df_budget.iterrows():
                buy_price = float(p['buy_price_yuan'])
                qty_needed = float(p['quantity_needed'])
                cost_full = buy_price * qty_needed
                
                # قانون ۱: زیر ۵۰۰۰ یوان (تغییر تعداد ممنوع - یا کل تعداد یا هیچی)
                if cost_full <= 5000:
                    if rem_budget >= cost_full:
                        suggested_qty = qty_needed
                        rem_budget -= cost_full
                        suggested.append((p, suggested_qty))
                # قانون ۲: بین ۵۰۰۱ تا ۱۰۰۰۰ یوان
                elif cost_full <= 10000:
                    if qty_needed < 100:
                        # زیر ۱۰۰ عدد (تغییر تعداد ممنوع)
                        if rem_budget >= cost_full:
                            suggested_qty = qty_needed
                            rem_budget -= cost_full
                            suggested.append((p, suggested_qty))
                    else:
                        # بالای ۱۰۰ عدد (کاهش مجاز است)
                        max_qty = int(rem_budget // buy_price)
                        suggested_qty = min(qty_needed, max_qty)
                        if suggested_qty > 0:
                            rem_budget -= (suggested_qty * buy_price)
                            suggested.append((p, suggested_qty))
                # قانون ۳: بالای ۱۰۰۰۰ یوان (کاهش تعداد همواره مجاز است)
                else:
                    max_qty = int(rem_budget // buy_price)
                    suggested_qty = min(qty_needed, max_qty)
                    if suggested_qty > 0:
                        rem_budget -= (suggested_qty * buy_price)
                        suggested.append((p, suggested_qty))
            
            if suggested:
                suggested_data = []
                total_cbm = 0.0
                total_shipping = 0.0
                total_processing = 0.0
                total_tax = 0.0
                total_yuan = 0.0
                total_profit = 0.0
                
                for p, s_qty in suggested:
                    cost_yuan = s_qty * p['buy_price_yuan']
                    
                    length = float(p['length_cm'])
                    width = float(p['width_cm'])
                    height = float(p['height_cm'])
                    pcs = int(p['pcs_per_carton'])
                    cbm_rate = float(p['cbm_rate_toman'])
                    
                    carton_cbm = (length * width * height) / 1000000
                    item_cbm = carton_cbm / pcs if pcs > 0 else 0
                    item_shipping = item_cbm * cbm_rate
                    
                    proc_fee, tax = calculate_fees(float(p['digikala_price_toman']), float(p['commission_percent']))
                    comm_amount = float(p['digikala_price_toman']) * (float(p['commission_percent']) / 100.0)
                    item_dk_net = float(p['digikala_price_toman']) - tax - comm_amount - proc_fee
                    item_cost_toman = (float(p['buy_price_yuan']) * yuan_rate) + item_shipping
                    item_profit = item_dk_net - item_cost_toman
                    
                    total_cbm += (item_cbm * s_qty)
                    total_shipping += (item_shipping * s_qty)
                    total_processing += (proc_fee * s_qty)
                    total_tax += (tax * s_qty)
                    total_yuan += cost_yuan
                    total_profit += (item_profit * s_qty)
                    
                    suggested_data.append({
                        "نام کالا": p['name'],
                        "تعداد پیشنهادی": f"{s_qty:.0f} از {p['quantity_needed']:.0f}",
                        "هزینه (یوان)": f"{cost_yuan:,.0f} ¥",
                        "درصد سود": f"{p['profit_percent']:.2f}%",
                        "CBM کل": f"{(item_cbm * s_qty):.4f}"
                    })
                
                st.table(pd.DataFrame(suggested_data))
                
                # محاسبه هزینه نهایی تا تهران
                total_yuan_toman = total_yuan * yuan_rate
                total_landed_cost = total_yuan_toman + total_shipping + total_processing + total_tax
                
                st.markdown(f"""
                <div style='background-color: #f8f9fa; padding: 20px; border-radius: 10px; border: 2px solid #0d6efd; margin-top: 15px;'>
                    <h4 style='color: #0d6efd; margin-top: 0;'>📋 خلاصه برآورد مالی و ترابری بار پیشنهادی</h4>
                    <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;'>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>باقیمانده بودجه:</p>
                            <strong style='font-size: 18px;'>{rem_budget:,.0f} ¥</strong>
                        </div>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>مجموع حجم بار (CBM):</p>
                            <strong style='font-size: 18px; color: #fd7e14;'>{total_cbm:.4f} CBM</strong>
                        </div>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>هزینه حمل تا انبار تهران:</p>
                            <strong style='font-size: 18px; color: #dc3545;'>{total_shipping:,.0f} تومان</strong>
                        </div>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>هزینه‌های جانبی دیجی (پردازش و مالیات):</p>
                            <strong style='font-size: 18px; color: #6f42c1;'>{(total_processing + total_tax):,.0f} تومان</strong>
                        </div>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>سود خالص پیش‌بینی شده:</p>
                            <strong style='font-size: 18px; color: #198754;'>{total_profit:,.0f} تومان</strong>
                        </div>
                        <div style='grid-column: 1 / -1; border-top: 1px solid #dee2e6; padding-top: 10px; margin-top: 5px;'>
                            <p style='margin: 0; color: #6c757d; font-size: 14px;'>💰 <b>هزینه تمام‌شده کل ریالی (خرید یوان + حمل + هزینه‌های دیجی):</b></p>
                            <strong style='font-size: 22px; color: #0d6efd;'>{total_landed_cost:,.0f} تومان</strong>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("با این بودجه پیشنهادی یافت نشد.")
        else:
            st.info("هیچ 'کالای درخواستی' برای محاسبه بودجه وجود ندارد.")
    else:
        st.info("لیست کالاها خالی است.")

with tabs[7]:
    st.subheader("📥 ورودی/خروجی اکسل")
    sample_df = pd.DataFrame({
        'نام کالا': ['نمونه'], 'دسته بندی': ['ورزشی'], 'وضعیت': ['کالاهای درخواستی'], 'لینک تامین': ['https://'], 
        'لینک دیجی': ['https://'], 'کد DKP': [''], 'تعداد': [10], 'قیمت خرید(یوان)': [50], 
        'تعداد در کارتن': [20], 'وزن هر کارتن': [10], 'هزینه CBM': [15000000], 'طول': [40], 'عرض': [30], 'ارتفاع': [20], 
        'قیمت فروش': [500000], 'کمیسیون(%)': [5]
    })
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        sample_df.to_excel(writer, index=False)
    st.download_button("دانلود اکسل نمونه", data=buffer.getvalue(), file_name="template.xlsx", mime="application/vnd.ms-excel")
    
    st.markdown("---")
    uploaded_file = st.file_uploader("فایل اکسل پر شده را آپلود کن", type=['xlsx'])
    
    if uploaded_file is not None and st.button("ثبت گروهی"):
        try:
            df_in = pd.read_excel(uploaded_file)
            df_all = get_products()
            
            added_lt_yuan = 0.0
            added_lt_shipping = 0.0
            added_lt_net_sales = 0.0
            
            new_rows = []
            
            current_max_id = 0
            if not df_all.empty and 'id' in df_all.columns:
                valid_ids = pd.to_numeric(df_all['id'], errors='coerce').dropna()
                if not valid_ids.empty:
                    current_max_id = int(valid_ids.max())
            
            for _, row in df_in.iterrows():
                status_val = str(row.get('وضعیت', 'کالاهای درخواستی'))
                qty_val = float(row.get('تعداد', 0))
                buy_val = float(row.get('قیمت خرید(یوان)', 0))
                l_val = float(row.get('طول', 0))
                w_val = float(row.get('عرض', 0))
                h_val = float(row.get('ارتفاع', 0))
                pcs_val = float(row.get('تعداد در کارتن', 1))
                cbm_rate_val = float(row.get('هزینه CBM', 0))
                dk_price = float(row.get('قیمت فروش', 0))
                comm = float(row.get('کمیسیون(%)', 0))
                
                proc_calc, tax_calc = calculate_fees(dk_price, comm)
                
                if status_val in ACTIVE_STATUSES:
                    added_lt_yuan += buy_val * qty_val
                    cbm = (l_val * w_val * h_val) / 1000000
                    pcs = pcs_val if pcs_val > 0 else 1
                    added_lt_shipping += (cbm / pcs) * cbm_rate_val * qty_val
                    
                    dk_net = dk_price - tax_calc - (dk_price * (comm / 100)) - proc_calc
                    added_lt_net_sales += dk_net * qty_val

                current_max_id += 1
                new_rows.append({
                    'id': current_max_id,
                    'name': str(row.get('نام کالا', '')),
                    'category': str(row.get('دسته بندی', '')),
                    'status': status_val,
                    'supplier_link': str(row.get('لینک تامین', '')),
                    'digikala_link': str(row.get('لینک دیجی', '')),
                    'dkp_code': str(row.get('کد DKP', '')),
                    'quantity_needed': qty_val,
                    'length_cm': l_val,
                    'width_cm': w_val,
                    'height_cm': h_val,
                    'pcs_per_carton': pcs_val,
                    'cbm_rate_toman': cbm_rate_val,
                    'buy_price_yuan': buy_val,
                    'digikala_price_toman': dk_price,
                    'tax_amount_toman': tax_calc,
                    'commission_percent': comm,
                    'processing_fee_toman': proc_calc,
                    'pure_profit_toman': 0.0,
                    'profit_percent': 0.0,
                    'carton_weight_kg': float(row.get('وزن هر کارتن', 0)),
                    'net_sales_toman': 0.0
                })
            
            if new_rows:
                df_all = pd.concat([df_all, pd.DataFrame(new_rows)], ignore_index=True)
                save_products(df_all)
            
            if added_lt_yuan > 0 or added_lt_shipping > 0 or added_lt_net_sales > 0:
                lt_settings = get_settings()
                lt_settings['lifetime_yuan'] = lt_settings.get('lifetime_yuan', 0.0) + added_lt_yuan
                lt_settings['lifetime_shipping'] = lt_settings.get('lifetime_shipping', 0.0) + added_lt_shipping
                lt_settings['lifetime_net_sales'] = lt_settings.get('lifetime_net_sales', 0.0) + added_lt_net_sales
                save_settings(lt_settings)
                
            st.success("اکسل با موفقیت وارد شد!")
            st.rerun()
        except Exception as e:
            st.error(f"خطا در ساختار فایل: {e}")