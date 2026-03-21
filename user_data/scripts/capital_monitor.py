#!/usr/bin/env python3
"""
资金利用率监控脚本
定期报告资金使用情况并提供建议
"""

import json
import time
from datetime import datetime
from pathlib import Path

# 配置
LOG_FILE = Path("/root/ft_userdata/user_data/logs/freqtrade.log")
REPORT_FILE = Path("/root/ft_userdata/user_data/logs/capital_report.log")
STATE_FILE = Path("/root/ft_userdata/user_data/scripts/capital_state.json")


def parse_utilization():
    """解析最新的资金利用率"""
    if not LOG_FILE.exists():
        return None

    try:
        with open(LOG_FILE, 'r') as f:
            # 读取最后10000行
            lines = f.readlines()[-10000:]

        utilization_data = []
        for line in lines:
            if 'UTILIZATION_CHECK' in line:
                try:
                    # 解析利用率
                    parts = line.split('Current utilization:')[1].split(',')[0]
                    util = float(parts.strip().replace('%', ''))
                    # 解析最大允许
                    max_parts = line.split('Max allowed:')[1].split('%')[0]
                    max_util = float(max_parts.strip())
                    timestamp = line.split(']')[0].replace('[', '')
                    utilization_data.append({
                        'timestamp': timestamp,
                        'utilization': util,
                        'max_allowed': max_util
                    })
                except:
                    continue

        return utilization_data[-10:] if utilization_data else None
    except Exception as e:
        print(f"解析错误: {e}")
        return None


def calculate_stats(utilization_data):
    """计算统计信息"""
    if not utilization_data:
        return None

    utils = [u['utilization'] for u in utilization_data]

    return {
        'current': utils[-1],
        'avg': sum(utils) / len(utils),
        'min': min(utils),
        'max': max(utils),
        'trend': '上升' if len(utils) > 1 and utils[-1] > utils[0] else '下降',
        'samples': len(utils)
    }


def generate_recommendation(stats):
    """生成优化建议"""
    if not stats:
        return "无法获取数据"

    recommendations = []
    current = stats['current']

    if current < 40:
        recommendations.append("🔴 资金利用率过低！建议:")
        recommendations.append("   - 降低入场条件阈值")
        recommendations.append("   - 增加交易对数量")
        recommendations.append("   - 增加单笔仓位大小")
        recommendations.append("   - 减少冷却时间")
    elif current < 55:
        recommendations.append("🟡 资金利用率偏低，建议:")
        recommendations.append("   - 适当降低入场条件")
        recommendations.append("   - 增加加仓频率")
    elif current < 70:
        recommendations.append("🟢 资金利用率正常")
        recommendations.append("   - 当前配置较为合理")
    elif current < 85:
        recommendations.append("🟡 资金利用率较高，注意风险")
        recommendations.append("   - 可适当收紧入场条件")
    else:
        recommendations.append("🔴 资金利用率过高！风险警告")
        recommendations.append("   - 建议减少加仓")
        recommendations.append("   - 考虑增加max_open_trades")

    recommendations.append(f"\n📊 统计信息:")
    recommendations.append(f"   - 当前利用率: {current:.1f}%")
    recommendations.append(f"   - 平均利用率: {stats['avg']:.1f}%")
    recommendations.append(f"   - 范围: {stats['min']:.1f}% - {stats['max']:.1f}%")
    recommendations.append(f"   - 趋势: {stats['trend']}")

    return '\n'.join(recommendations)


def main():
    """主函数"""
    print(f"[{datetime.now()}] 资金利用率监控启动")

    while True:
        try:
            # 解析利用率
            utilization_data = parse_utilization()

            if utilization_data:
                stats = calculate_stats(utilization_data)
                report = generate_recommendation(stats)

                # 输出报告
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                full_report = f"\n{'='*50}\n[{now}]\n{report}"
                print(full_report)

                # 保存到文件
                with open(REPORT_FILE, 'a') as f:
                    f.write(full_report + '\n')

            # 每5分钟检查一次
            time.sleep(300)

        except KeyboardInterrupt:
            print("\n监控停止")
            break
        except Exception as e:
            print(f"监控异常: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()