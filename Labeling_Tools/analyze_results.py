"""
Script phân tích kết quả sau khi gán nhãn
"""

import pandas as pd
import json
from collections import Counter

def load_labeled_data(file_path: str = "Data/du_lieu_ai_gan_nhan.csv"):
    """Load dữ liệu đã được gán nhãn"""
    try:
        df = pd.read_csv(file_path)
        return df
    except FileNotFoundError:
        print(f"❌ Không tìm thấy file: {file_path}")
        print("Vui lòng chạy Gemini_label.py trước!")
        return None

def display_overview(df: pd.DataFrame):
    """Hiển thị tổng quan"""
    print("\n" + "="*60)
    print("📊 TỔNG QUAN")
    print("="*60)
    print(f"Tổng số bài viết: {len(df)}")
    print(f"Đã gán nhãn: {df['label'].notna().sum()}")
    print(f"Chưa gán nhãn: {df['label'].isna().sum()}")

def display_label_distribution(df: pd.DataFrame):
    """Hiển thị phân bố nhãn"""
    print("\n" + "="*60)
    print("🏷️  PHÂN BỐ NHÃN")
    print("="*60)
    
    if 'label' not in df.columns or df['label'].isna().all():
        print("Chưa có dữ liệu nhãn")
        return
    
    label_counts = df['label'].value_counts()
    total = len(df[df['label'].notna()])
    
    for label, count in label_counts.items():
        percentage = (count / total * 100) if total > 0 else 0
        bar_length = int(percentage / 2)
        bar = "█" * bar_length
        print(f"\n{label}:")
        print(f"  Số lượng: {count:>4} ({percentage:>5.1f}%)")
        print(f"  {bar}")

def display_confidence_distribution(df: pd.DataFrame):
    """Hiển thị phân bố độ tin cậy"""
    print("\n" + "="*60)
    print("🎯 ĐỘ TIN CẬY")
    print("="*60)
    
    if 'confidence' not in df.columns or df['confidence'].isna().all():
        print("Không có dữ liệu độ tin cậy")
        return
    
    confidence_counts = df['confidence'].value_counts()
    total = len(df[df['confidence'].notna()])
    
    for conf, count in confidence_counts.items():
        percentage = (count / total * 100) if total > 0 else 0
        print(f"{conf:>8}: {count:>4} ({percentage:>5.1f}%)")

def display_sample_by_label(df: pd.DataFrame, n: int = 3):
    """Hiển thị mẫu từng nhãn"""
    print("\n" + "="*60)
    print(f"📝 MẪU BÀI VIẾT THEO TỪNG NHÃN (Top {n})")
    print("="*60)
    
    if 'label' not in df.columns or df['label'].isna().all():
        print("Chưa có dữ liệu nhãn")
        return
    
    labels = df['label'].dropna().unique()
    
    for label in labels:
        print(f"\n{'-'*60}")
        print(f"📌 {label}")
        print(f"{'-'*60}")
        
        label_df = df[df['label'] == label].head(n)
        
        for idx, row in label_df.iterrows():
            print(f"\n{idx+1}. {row['title']}")
            if 'confidence' in row and pd.notna(row['confidence']):
                print(f"   Độ tin cậy: {row['confidence']}")
            if 'reasoning' in row and pd.notna(row['reasoning']):
                reasoning = str(row['reasoning'])[:150]
                print(f"   Lý do: {reasoning}...")

def display_low_confidence_items(df: pd.DataFrame, n: int = 5):
    """Hiển thị các bài viết có độ tin cậy thấp"""
    print("\n" + "="*60)
    print(f"⚠️  BÀI VIẾT CẦN REVIEW (Độ tin cậy thấp - Top {n})")
    print("="*60)
    
    if 'confidence' not in df.columns:
        print("Không có dữ liệu độ tin cậy")
        return
    
    low_conf = df[df['confidence'] == 'low'].head(n)
    
    if len(low_conf) == 0:
        print("✅ Không có bài viết nào có độ tin cậy thấp")
        return
    
    for idx, row in low_conf.iterrows():
        print(f"\n{idx+1}. {row['title']}")
        print(f"   Nhãn: {row['label']}")
        if 'reasoning' in row and pd.notna(row['reasoning']):
            print(f"   Lý do: {row['reasoning']}")

def export_by_label(df: pd.DataFrame, output_dir: str = "Data/labeled_by_category"):
    """Export dữ liệu theo từng nhãn ra file riêng"""
    import os
    
    if 'label' not in df.columns or df['label'].isna().all():
        print("Chưa có dữ liệu nhãn để export")
        return
    
    # Tạo thư mục nếu chưa có
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n" + "="*60)
    print("💾 EXPORT DỮ LIỆU THEO NHÃN")
    print("="*60)
    
    labels = df['label'].dropna().unique()
    
    for label in labels:
        label_df = df[df['label'] == label]
        
        # Tạo tên file an toàn
        safe_filename = label.replace(" ", "_").replace("&", "and").lower()
        output_path = os.path.join(output_dir, f"{safe_filename}.csv")
        
        label_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"✓ Đã lưu {len(label_df)} bài viết vào: {output_path}")

def generate_summary_report(df: pd.DataFrame):
    """Tạo báo cáo tóm tắt"""
    print("\n" + "="*60)
    print("📋 BÁO CÁO TÓM TẮT")
    print("="*60)
    
    report = {
        "total_articles": len(df),
        "labeled_articles": df['label'].notna().sum(),
        "unlabeled_articles": df['label'].isna().sum(),
    }
    
    if 'label' in df.columns and df['label'].notna().any():
        label_dist = df['label'].value_counts().to_dict()
        report["label_distribution"] = label_dist
    
    if 'confidence' in df.columns and df['confidence'].notna().any():
        conf_dist = df['confidence'].value_counts().to_dict()
        report["confidence_distribution"] = conf_dist
    
    # Hiển thị report
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    # Lưu report ra file
    report_path = "Data/labeling_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Đã lưu báo cáo chi tiết vào: {report_path}")

def analyze_label_quality(df: pd.DataFrame):
    """Phân tích chất lượng gán nhãn"""
    print("\n" + "="*60)
    print("🔍 PHÂN TÍCH CHẤT LƯỢNG")
    print("="*60)
    
    if 'confidence' not in df.columns:
        print("Không có dữ liệu độ tin cậy để phân tích")
        return
    
    total = len(df[df['label'].notna()])
    high_conf = len(df[df['confidence'] == 'high'])
    medium_conf = len(df[df['confidence'] == 'medium'])
    low_conf = len(df[df['confidence'] == 'low'])
    
    print(f"\nChất lượng tổng thể:")
    print(f"  Độ tin cậy cao:    {high_conf:>4} ({high_conf/total*100:>5.1f}%)")
    print(f"  Độ tin cậy trung:  {medium_conf:>4} ({medium_conf/total*100:>5.1f}%)")
    print(f"  Độ tin cậy thấp:   {low_conf:>4} ({low_conf/total*100:>5.1f}%)")
    
    quality_score = (high_conf * 1.0 + medium_conf * 0.5 + low_conf * 0.0) / total * 100
    print(f"\n📊 Điểm chất lượng: {quality_score:.1f}/100")
    
    if quality_score >= 80:
        print("   ✅ Xuất sắc! Chất lượng gán nhãn rất tốt")
    elif quality_score >= 60:
        print("   ⚠️  Khá tốt, nhưng nên review lại một số bài viết")
    else:
        print("   ❌ Cần review lại nhiều bài viết")

def main():
    """Hàm main"""
    print("="*60)
    print("📊 PHÂN TÍCH KẾT QUẢ GÁN NHÃN")
    print("="*60)
    
    # Load dữ liệu
    df = load_labeled_data("Data/du_lieu_ai_gan_nhan.csv")
    
    if df is None:
        return
    
    # Các phân tích
    display_overview(df)
    display_label_distribution(df)
    display_confidence_distribution(df)
    analyze_label_quality(df)
    display_sample_by_label(df, n=3)
    display_low_confidence_items(df, n=5)
    
    # Export theo nhãn
    print("\n" + "="*60)
    export_choice = input("Bạn có muốn export dữ liệu theo từng nhãn? (y/n): ").lower()
    if export_choice == 'y':
        export_by_label(df)
    
    # Tạo báo cáo tóm tắt
    generate_summary_report(df)
    
    print("\n" + "="*60)
    print("✅ HOÀN THÀNH PHÂN TÍCH")
    print("="*60)

if __name__ == "__main__":
    main()
