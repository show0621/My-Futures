# 請將此段邏輯加入 update_data.py 的損益計算循環中
for name, sig_col in strat_list:
    df[f'Pos_{name}'] = np.floor(2 * df['Risk_Leverage']).clip(1, 5)
    
    # 點數差額
    raw_points = np.where(df[sig_col] == 1, df['Exit_Price'] - df['Entry_Price'], 
                 np.where(df[sig_col] == -1, df['Entry_Price'] - df['Exit_Price'], 0))

    # 1. 原有的「純買方」損益
    df[f'{name}_PnL_TWD'] = (raw_points * 0.5 * 50 * df[f'Pos_{name}']) - (100 * df[f'Pos_{name}'])
    
    # 2. 新增「價差策略」損益 (Bull Call / Bear Put Spread)
    # 價差策略通常 Delta 較低 (約 0.25)，但權利金成本也減半
    df[f'{name}_Spread_PnL_TWD'] = (raw_points * 0.25 * 50 * df[f'Pos_{name}']) - (150 * df[f'Pos_{name}']) # 手續費略高
    
    df[f'{name}_PnL_TWD'] = df[f'{name}_PnL_TWD'].fillna(0)
    df[f'{name}_Spread_PnL_TWD'] = df[f'{name}_Spread_PnL_TWD'].fillna(0)
