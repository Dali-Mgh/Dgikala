import streamlit as st
import pandas as pd
import io
import requests
from bs4 import BeautifulSoup
import gspread

st.set_page_config(page_title="مدیریت هوشمند خرید", layout="wide")

# ================= تنظیمات گوگل شیت =================
# ⚠️ لینک فایل گوگل شیت خود را دقیقاً اینجا بین دو کوتیشن قرار دهید:
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1IniJrxUUYOqpEr8EP6DpOyoiAHxa3DabLgpszgdmHrk/edit?usp=sharing"

@st.cache_resource
def get_gsheet():
    if SPREADSHEET_URL == "لینک_فایل_گوگل_شیت_خود_را_اینجا_قرار_دهید":
        st.error("لطفا ابتدا لینک گوگل شیت را در متغیر SPREADSHEET_URL (خط 10 کد) وارد کنید!")
        st.stop()
    try:
        credentials = dict(st.secrets["gcp_service_account"])
        gc = gspread.service_account_from_dict(credentials)
        sh = gc.open_by_url(SPREADSHEET_URL)
        return sh
    except Exception as e:
        st.error(f"خطا در اتصال به گوگل شیت. آیا ایمیل به فایل اضافه شده است؟ \n {e}")
        st.stop()

def init_db():
    sh = get_gsheet()
    # ساخت شیت محصولات در صورت عدم وجود
    try:
        sh.worksheet("products")
    except gspread.WorksheetNotFound:
        ws_products = sh.add_worksheet(title="products", rows="100", cols="25")
        headers = ["id", "name", "category", "status", "supplier_link", "digikala_link", "dkp_code", 
                   "quantity_needed", "length_cm", "width_cm", "height_cm", "pcs_per_carton", 
                   "cbm_rate_toman", "buy_price_yuan", "digikala_price_toman", "tax_amount_toman", 
                   "commission_percent", "processing_fee_toman", "pure_profit_toman", "profit_percent", 
                   "carton_weight_kg", "net_sales_toman"]
        ws_products.append_row(headers)
    
    # ساخت شیت تنظیمات در صورت عدم وجود
    try:
        sh.worksheet("settings")
    except gspread.WorksheetNotFound:
        ws_settings = sh.add_worksheet(title="settings", rows="10", cols="2")
        ws_settings.append_row(["key", "value"])
        ws_settings.append_rows([
            ["yuan_rate", 9000.0],
            ["lifetime_yuan", 0.0],
            ["lifetime_shipping", 0.0],
            ["lifetime_net_sales", 0.0]
        ])

# توابع کمکی دیتابیس گوگل شیت
def get_settings():
    sh = get_gsheet()
    ws = sh.worksheet("settings")
    records = ws.get_all_records()
    return {str(r['key']): float(r['value']) if r['value'] else 0.0 for r in records}

def update_setting(key, value, increment=False):
    sh = get_gsheet()
    ws = sh.worksheet("settings")
    records = ws.get_all_records()
    cell_row = None
    current_val = 0.0
    for i, r in enumerate(records):
        if r['key'] == key:
            cell_row = i + 2
            current_val = float(r['value']) if r['value'] else 0.0
            break
    
    final_value = current_val + value if increment else value
    if cell_row:
        ws.update_cell(cell_row, 2, final_value)
    else:
        ws.append_row([key, final_value])

def get_products():
    sh = get_gsheet()
    ws = sh.worksheet("products")
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=["id", "name", "category", "status", "supplier_link", "digikala_link", "dkp_code", 
                   "quantity_needed", "length_cm", "width_cm", "height_cm", "pcs_per_carton", 
                   "cbm_rate_toman", "buy_price_yuan", "digikala_price_toman", "tax_amount_toman", 
                   "commission_percent", "processing_fee_toman", "pure_profit_toman", "profit_percent", 
                   "carton_weight_kg", "net_sales_toman"])
    df = pd.DataFrame(records)
    return df

def save_products(df):
    sh = get_gsheet()
    ws = sh.worksheet("products")
    ws.clear()
    df = df.fillna("")
    data = [df.columns.values.tolist()] + df.values.tolist()
    ws.update(range_name='A1', values=data)

STATUS_OPTIONS = ["کالاهای درخواستی", "کالاهای ارسال شده", "کالاهای موجود"]

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

# راه‌اندازی دیتابیس
init_db()
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
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fa,en-US;q=0.9,en;q=0.8',
            'Referer': 'https://www.google.com/'
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
            update_setting('yuan_rate', live_price)
            st.success(f"آپدیت شد: {live_price:,} تومان")
            st.rerun()
        else:
            st.error("خطا در دریافت قیمت. سایت مبدا پاسخگو نیست.")

    yuan_rate = st.number_input("نرخ روز یوان (تومان):", value=int(saved_yuan), step=100)
    if st.button("💾 ذخیره قیمت دستی"):
        update_setting('yuan_rate', yuan_rate)
        st.success("قیمت جدید ثبت شد!")
        st.rerun()

    st.markdown("---")
    st.subheader("تنظیمات آمار")
    if st.button("⚠️ صفر کردن کنتور انباشتی خرید"):
        update_setting('lifetime_yuan', 0.0)
        update_setting('lifetime_shipping', 0.0)
        update_setting('lifetime_net_sales', 0.0)
        st.success("آمار کنتور صفر شد!")
        st.rerun()


# ================= توابع محاسباتی =================
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
        tax = float(row['tax_amount_toman'])
        comm_pct = float(row['commission_percent'])
        proc_fee = float(row['processing_fee_toman'])
        
        carton_cbm = (length * width * height) / 1000000
        item_cbm = carton_cbm / pcs if pcs > 0 else 0
        item_shipping_toman = item_cbm * cbm_rate
        item_cost_toman = (price_yuan * current_yuan) + item_shipping_toman
        
        item_dk_net = dk_price - tax - (dk_price * (comm_pct / 100)) - proc_fee
        
        item_profit = item_dk_net - item_cost_toman
        total_net_profit = item_profit * qty
        
        profit_margin_pct = (item_profit / dk_price) * 100 if dk_price > 0 else 0
        
        return pd.Series([total_net_profit, profit_margin_pct, item_dk_net])
    except:
        return pd.Series([0.0, 0.0, 0.0])

def render_product_table(df_subset, tab_key):
    if df_subset.empty:
        st.info("لیست کالاها در این بخش خالی است.")
        return
        
    st.info("💡 برای ویرایش اطلاعات، روی سلول‌ها کلیک کنید. در پایان حتماً دکمه ذخیره را بزنید.")
    
    display_df = df_subset.copy()
    display_df['cbm_rate_toman'] = display_df['cbm_rate_toman'].map('{:,.0f}'.format)
    display_df['digikala_price_toman'] = display_df['digikala_price_toman'].map('{:,.0f}'.format)
    display_df['tax_amount_toman'] = display_df['tax_amount_toman'].map('{:,.0f}'.format)
    display_df['processing_fee_toman'] = display_df['processing_fee_toman'].map('{:,.0f}'.format)
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
            "pcs_per_carton", "cbm_per_carton", "cbm_rate_toman", "buy_price_yuan",
            "digikala_price_toman", "commission_percent", "processing_fee_toman",
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
            "buy_price_yuan": st.column_config.NumberColumn("قیمت خرید(یوان)"),
            "digikala_price_toman": st.column_config.TextColumn("قیمت فروش (تومان)"),
            "tax_amount_toman": st.column_config.TextColumn("مالیات (تومان)"),
            "commission_percent": st.column_config.NumberColumn("کمیسیون (%)"),
            "processing_fee_toman": st.column_config.TextColumn("هزینه پردازش (تومان)"),
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
        
        added_lt_yuan = 0.0
        added_lt_shipping = 0.0
        added_lt_net_sales = 0.0

        for _, row in edited_df.iterrows():
            orig_row = df_subset[df_subset['id'] == row['id']].iloc[0]
            
            cbm_clean = float(str(row['cbm_rate_toman']).replace(',', ''))
            dk_clean = float(str(row['digikala_price_toman']).replace(',', ''))
            tax_clean = float(str(row['tax_amount_toman']).replace(',', ''))
            proc_clean = float(str(row['processing_fee_toman']).replace(',', ''))
            
            if orig_row['status'] == 'کالاهای درخواستی' and row['status'] in ['کالاهای ارسال شده', 'کالاهای موجود']:
                added_lt_yuan += float(row['buy_price_yuan'] * row['quantity_needed'])
                cbm = (row['length_cm'] * row['width_cm'] * row['height_cm']) / 1000000
                pcs = row['pcs_per_carton'] if row['pcs_per_carton'] > 0 else 1
                added_lt_shipping += float((cbm / pcs) * cbm_clean * row['quantity_needed'])
                
                dk_net_single = dk_clean - tax_clean - (dk_clean * (row['commission_percent'] / 100)) - proc_clean
                added_lt_net_sales += float(dk_net_single * row['quantity_needed'])

            # آپدیت در دیتافریم کلی
            idx = df_all.index[df_all['id'] == row['id']].tolist()
            if idx:
                i = idx[0]
                df_all.at[i, 'name'] = row['name']
                df_all.at[i, 'category'] = row['category']
                df_all.at[i, 'status'] = row['status']
                df_all.at[i, 'supplier_link'] = row['supplier_link']
                df_all.at[i, 'digikala_link'] = row['digikala_link']
                df_all.at[i, 'dkp_code'] = row['dkp_code']
                df_all.at[i, 'quantity_needed'] = row['quantity_needed']
                df_all.at[i, 'length_cm'] = row['length_cm']
                df_all.at[i, 'width_cm'] = row['width_cm']
                df_all.at[i, 'height_cm'] = row['height_cm']
                df_all.at[i, 'pcs_per_carton'] = row['pcs_per_carton']
                df_all.at[i, 'cbm_rate_toman'] = cbm_clean
                df_all.at[i, 'buy_price_yuan'] = row['buy_price_yuan']
                df_all.at[i, 'digikala_price_toman'] = dk_clean
                df_all.at[i, 'tax_amount_toman'] = tax_clean
                df_all.at[i, 'commission_percent'] = row['commission_percent']
                df_all.at[i, 'processing_fee_toman'] = proc_clean
                df_all.at[i, 'carton_weight_kg'] = row['carton_weight_kg']
            
        save_products(df_all)
        
        if added_lt_yuan > 0: update_setting('lifetime_yuan', added_lt_yuan, True)
        if added_lt_shipping > 0: update_setting('lifetime_shipping', added_lt_shipping, True)
        if added_lt_net_sales > 0: update_setting('lifetime_net_sales', added_lt_net_sales, True)
            
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
tabs = st.tabs(["📋 کل کالاها", "🛒 درخواستی", "✈️ ارسال شده", "📦 موجود", "➕ افزودن جدید", "💡 پیشنهاد خرید", "📥 اکسل"])

df = get_products()

if not df.empty:
    df[['pure_profit_toman', 'profit_percent', 'net_sales_toman']] = df.apply(lambda r: dynamic_calc(r, yuan_rate), axis=1)
    df['cbm_per_carton'] = (pd.to_numeric(df['length_cm']) * pd.to_numeric(df['width_cm']) * pd.to_numeric(df['height_cm'])) / 1000000
    
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

with tabs[0]: 
    render_product_table(df, "all")
with tabs[1]: 
    if not df.empty:
        render_product_table(df[df['status'] == 'کالاهای درخواستی'], "req")
    else:
        st.info("لیست کالاها در این بخش خالی است.")
with tabs[2]: 
    if not df.empty:
        render_product_table(df[df['status'] == 'کالاهای ارسال شده'], "sent")
    else:
        st.info("لیست کالاها در این بخش خالی است.")
with tabs[3]: 
    if not df.empty:
        render_product_table(df[df['status'] == 'کالاهای موجود'], "stock")
    else:
        st.info("لیست کالاها در این بخش خالی است.")

with tabs[4]:
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
        
        col14, col15, col16, col17 = st.columns(4)
        dk_price = col14.number_input("قیمت فروش (تومان)", min_value=0.0, value=200000.0)
        tax = col15.number_input("مالیات (تومان)", min_value=0.0, value=0.0)
        comm = col16.number_input("کمیسیون (%)", min_value=0.0, value=5.0)
        proc_fee = col17.number_input("هزینه پردازش (تومان)", min_value=0.0, value=5000.0)
        
        if st.form_submit_button("ثبت کالا"):
            df_all = get_products()
            new_id = int(df_all['id'].max()) + 1 if not df_all.empty and 'id' in df_all.columns else 1
            
            new_row = {
                'id': new_id, 'name': name, 'category': category, 'status': status, 
                'supplier_link': sup_link, 'digikala_link': dk_link, 'dkp_code': dkp, 
                'quantity_needed': qty, 'length_cm': length, 'width_cm': width, 'height_cm': height, 
                'pcs_per_carton': pcs_carton, 'cbm_rate_toman': cbm_rate, 'buy_price_yuan': buy_price, 
                'digikala_price_toman': dk_price, 'tax_amount_toman': tax, 'commission_percent': comm, 
                'processing_fee_toman': proc_fee, 'pure_profit_toman': 0, 'profit_percent': 0, 
                'carton_weight_kg': weight, 'net_sales_toman': 0
            }
            
            df_all = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
            save_products(df_all)
            
            if status in ['کالاهای ارسال شده', 'کالاهای موجود']:
                added_yuan = buy_price * qty
                cbm = (length * width * height) / 1000000
                pcs = pcs_carton if pcs_carton > 0 else 1
                added_shipping = (cbm / pcs) * cbm_rate * qty
                added_net_sales = (dk_price - tax - (dk_price * (comm / 100)) - proc_fee) * qty
                
                update_setting('lifetime_yuan', added_yuan, True)
                update_setting('lifetime_shipping', added_shipping, True)
                update_setting('lifetime_net_sales', added_net_sales, True)
                
            st.success("کالا ثبت شد!")
            st.rerun()

with tabs[5]:
    st.subheader("تخصیص هوشمند بودجه (مخصوص کالاهای درخواستی)")
    budget = st.number_input("بودجه (یوان):", min_value=0, value=30000, step=1000)
    
    if not df.empty:
        df_budget = df[df['status'] == 'کالاهای درخواستی'].copy()
        if not df_budget.empty:
            df_budget = df_budget.sort_values(by='profit_percent', ascending=False)
            
            suggested, rem_budget, total_profit = [], budget, 0
            for _, p in df_budget.iterrows():
                cost = p['buy_price_yuan'] * p['quantity_needed']
                if rem_budget >= cost:
                    suggested.append({"نام کالا": p['name'], "تعداد": p['quantity_needed'], "هزینه (یوان)": cost, "درصد سود": f"{p['profit_percent']:.2f}%"})
                    rem_budget -= cost
                    total_profit += p['pure_profit_toman']
                    
            if suggested:
                for i in range(len(suggested)):
                    suggested[i]["هزینه (یوان)"] = f'{suggested[i]["هزینه (یوان)"]:,.0f}'
                st.table(pd.DataFrame(suggested))
                st.success(f"باقیمانده بودجه: {rem_budget:,.0f} یوان")
                st.info(f"مجموع سود خالص این خرید: {total_profit:,.0f} تومان")
            else:
                st.warning("با این بودجه پیشنهادی یافت نشد.")
        else:
            st.info("هیچ 'کالای درخواستی' برای محاسبه بودجه وجود ندارد.")
    else:
        st.info("لیست کالاها خالی است.")

with tabs[6]:
    st.subheader("📥 ورودی/خروجی اکسل")
    sample_df = pd.DataFrame({
        'نام کالا': ['نمونه'], 'دسته بندی': ['ورزشی'], 'وضعیت': ['کالاهای درخواستی'], 'لینک تامین': ['https://'], 
        'لینک دیجی': ['https://'], 'کد DKP': [''], 'تعداد': [10], 'قیمت خرید(یوان)': [50], 
        'تعداد در کارتن': [20], 'وزن هر کارتن': [10], 'هزینه CBM': [15000000], 'طول': [40], 'عرض': [30], 'ارتفاع': [20], 
        'قیمت فروش': [500000], 'مالیات': [0], 'کمیسیون(%)': [5], 'هزینه پردازش': [5000]
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
            current_max_id = int(df_all['id'].max()) if not df_all.empty and 'id' in df_all.columns else 0
            
            for _, row in df_in.iterrows():
                status_val = str(row.get('وضعیت', 'کالاهای درخواستی'))
                qty_val = int(row.get('تعداد', 0))
                buy_val = float(row.get('قیمت خرید(یوان)', 0))
                l_val = float(row.get('طول', 0))
                w_val = float(row.get('عرض', 0))
                h_val = float(row.get('ارتفاع', 0))
                pcs_val = int(row.get('تعداد در کارتن', 1))
                cbm_rate_val = float(row.get('هزینه CBM', 0))
                
                if status_val in ['کالاهای ارسال شده', 'کالاهای موجود']:
                    added_lt_yuan += buy_val * qty_val
                    cbm = (l_val * w_val * h_val) / 1000000
                    pcs = pcs_val if pcs_val > 0 else 1
                    added_lt_shipping += (cbm / pcs) * cbm_rate_val * qty_val
                    
                    dk_price = float(row.get('قیمت فروش', 0))
                    tax = float(row.get('مالیات', 0))
                    comm = float(row.get('کمیسیون(%)', 0))
                    proc_fee = float(row.get('هزینه پردازش', 0))
                    dk_net = dk_price - tax - (dk_price * (comm / 100)) - proc_fee
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
                    'digikala_price_toman': float(row.get('قیمت فروش', 0)),
                    'tax_amount_toman': float(row.get('مالیات', 0)),
                    'commission_percent': float(row.get('کمیسیون(%)', 0)),
                    'processing_fee_toman': float(row.get('هزینه پردازش', 0)),
                    'pure_profit_toman': 0,
                    'profit_percent': 0,
                    'carton_weight_kg': float(row.get('وزن هر کارتن', 0)),
                    'net_sales_toman': 0
                })
            
            if new_rows:
                df_all = pd.concat([df_all, pd.DataFrame(new_rows)], ignore_index=True)
                save_products(df_all)
            
            if added_lt_yuan > 0: update_setting('lifetime_yuan', added_lt_yuan, True)
            if added_lt_shipping > 0: update_setting('lifetime_shipping', added_lt_shipping, True)
            if added_lt_net_sales > 0: update_setting('lifetime_net_sales', added_lt_net_sales, True)
                
            st.success("اکسل با موفقیت وارد شد!")
            st.rerun()
        except Exception as e:
            st.error(f"خطا در ساختار فایل: {e}")