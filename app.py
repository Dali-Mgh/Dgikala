# ... existing code ...
            if suggested:
                suggested_data = []
                total_cbm = 0.0
                total_shipping = 0.0
                total_processing = 0.0
                total_tax = 0.0
                total_yuan = 0.0
                total_profit = 0.0
                total_weight = 0.0
                
                for p, s_qty in suggested:
                    cost_yuan = s_qty * p['buy_price_yuan']
                    
                    length = float(p['length_cm'])
                    width = float(p['width_cm'])
                    height = float(p['height_cm'])
                    pcs = int(p['pcs_per_carton'])
                    cbm_rate = float(p['cbm_rate_toman'])
                    carton_weight = float(p.get('carton_weight_kg', 0.0))
                    
                    carton_cbm = (length * width * height) / 1000000
                    item_cbm = carton_cbm / pcs if pcs > 0 else 0
                    item_weight = carton_weight / pcs if pcs > 0 else 0
                    item_shipping = item_cbm * cbm_rate
                    
                    proc_fee, tax = calculate_fees(float(p['digikala_price_toman']), float(p['commission_percent']))
                    comm_amount = float(p['digikala_price_toman']) * (float(p['commission_percent']) / 100.0)
                    item_dk_net = float(p['digikala_price_toman']) - tax - comm_amount - proc_fee
                    item_cost_toman = (float(p['buy_price_yuan']) * yuan_rate) + item_shipping
                    item_profit = item_dk_net - item_cost_toman
                    
                    total_cbm += (item_cbm * s_qty)
                    total_weight += (item_weight * s_qty)
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
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>بودجه مصرف‌شده:</p>
                            <strong style='font-size: 18px; color: #20c997;'>{total_yuan:,.0f} ¥</strong>
                        </div>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>باقیمانده بودجه:</p>
                            <strong style='font-size: 18px;'>{rem_budget:,.0f} ¥</strong>
                        </div>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>مجموع حجم بار (CBM):</p>
                            <strong style='font-size: 18px; color: #fd7e14;'>{total_cbm:.4f} CBM</strong>
                        </div>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>مجموع وزن بار:</p>
                            <strong style='font-size: 18px; color: #6f42c1;'>{total_weight:,.2f} kg</strong>
                        </div>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>هزینه حمل تا انبار تهران:</p>
                            <strong style='font-size: 18px; color: #dc3545;'>{total_shipping:,.0f} تومان</strong>
                        </div>
                        <div>
                            <p style='margin: 0; color: #6c757d; font-size: 13px;'>هزینه‌های جانبی دیجی (پردازش و مالیات):</p>
                            <strong style='font-size: 18px; color: #6610f2;'>{(total_processing + total_tax):,.0f} تومان</strong>
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
# ... existing code ...