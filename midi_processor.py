import os
import mido
from typing import List, Dict, Tuple, Any, Optional
import time
import json

class MidiProcessor:
    def __init__(self):
        self.original_tempo = None
        self.tempo_changes = []
        self.debug_mode = True  # 启用详细日志输出
        self.detailed_tempos = []  # 存储详细的速度信息
        self.velocity_percent = 80  # 默认力度百分比
        
    def process_file(self, 
                    input_file: str, 
                    output_dir: str, 
                    target_bpm: float = 120.0, 
                    remove_cc: bool = True, 
                    set_velocity: bool = True,
                    velocity_percent: int = 80,
                    skip_matched: bool = True,
                    keep_original_tempo: bool = True,
                    check_overlap: bool = False,
                    fix_overlap: bool = False,
                    multitrack_overlap: bool = False) -> Dict[str, Any]:
        """
        处理单个MIDI文件
        
        Args:
            input_file: 输入MIDI文件路径
            output_dir: 输出目录
            target_bpm: 目标BPM
            remove_cc: 是否删除控制消息
            set_velocity: 是否设置固定力度
            velocity_percent: 力度百分比(1-100)
            skip_matched: 如果文件已匹配条件则跳过处理
            keep_original_tempo: 是否启用MIDI速度转换（True=启用转换，False=保持原始速度）
            check_overlap: 是否检测音符重叠
            fix_overlap: 是否处理重叠音符
            multitrack_overlap: 是否处理跨轨道重叠（True=全局处理，False=分轨道处理）
            
        Returns:
            包含处理结果信息的字典
        """
        try:
            print(f"\n开始处理文件: {input_file}")
            
            # 设置力度百分比
            self.velocity_percent = velocity_percent
            
            # 重置状态
            self.original_tempo = None
            self.tempo_changes = []
            self.detailed_tempos = []
            
            # 加载MIDI文件
            midi = mido.MidiFile(input_file)
            print(f"MIDI格式: {midi.type}, Ticks per beat: {midi.ticks_per_beat}")
            
            # 分析原始速度信息 - 直接从文件中读取
            print("\n===== 原始MIDI分析 =====")
            self._analyze_tempo(midi)
            
            # 计算实际力度值 (将百分比正确转换为MIDI力度值，范围1-127)
            target_velocity = min(127, max(1, int(127 * velocity_percent / 100)))

            # 检查是否需要处理
            needs_processing = True
            cc_status = "已处理" if remove_cc else "未处理"  # 默认状态基于选项
            velocity_status = "已处理" if set_velocity else "未处理"  # 默认状态基于选项
            overlap_status = "未检测"  # 默认重叠检测状态
            
            # 检查MIDI是否为变速（有多个不同的速度变化）
            has_multiple_tempos = False
            if len(self.tempo_changes) > 1:
                # 获取所有不同的速度值
                unique_tempos = set(tempo for _, tempo in self.tempo_changes)
                has_multiple_tempos = len(unique_tempos) > 1
                
            # 检查原始BPM是否与目标BPM一致（仅对非变速MIDI进行检查）
            original_bpm = self._tempo_to_bpm(self.original_tempo) if self.original_tempo else 120
            bpm_matches = False
            
            # 只有当MIDI有且仅有一个速度信息，且该速度与目标速度一致时，才认为BPM匹配
            if not has_multiple_tempos:
                bpm_matches = abs(original_bpm - target_bpm) < 0.1  # 允许0.1的误差
            else:
                # 变速MIDI始终需要处理
                bpm_matches = False
            
            # 检查文件是否包含任何控制消息
            has_cc_messages = False
            for track in midi.tracks:
                for msg in track:
                    if msg.type in ['control_change', 'pitchwheel', 'program_change', 
                                  'aftertouch', 'polytouch', 'sysex']:
                        has_cc_messages = True
                        break
                if has_cc_messages:
                    break
            
            # 检查音符力度是否已经是目标力度
            all_notes_match_velocity = True
            has_notes = False
            for track in midi.tracks:
                for msg in track:
                    if msg.type == 'note_on' and msg.velocity > 0:
                        has_notes = True
                        if abs(msg.velocity - target_velocity) > 3:  # 允许小误差
                            all_notes_match_velocity = False
                            break
                if has_notes and not all_notes_match_velocity:
                    break
            
            # 根据检查结果确定处理状态
            if bpm_matches:
                # 原始BPM与目标BPM匹配的情况
                
                # 1. 已勾选移除控制消息，但MIDI内不含控制信息
                if remove_cc and not has_cc_messages:
                    cc_status = "无需处理"
                
                # 2. 勾选了移除控制消息，且MIDI内包含控制消息需要移除
                elif remove_cc and has_cc_messages:
                    cc_status = "已处理"
                
                # 3. 未勾选移除控制消息
                else:  # not remove_cc
                    cc_status = "未处理"
                    
                # 设置音符力度状态
                if set_velocity:
                    if all_notes_match_velocity:
                        velocity_status = "无需处理"
                    else:
                        velocity_status = "已处理"
                else:
                    velocity_status = "未处理"
                
                # 如果BPM匹配且勾选了跳过匹配文件，则检查是否需要处理控制信息
                if skip_matched:
                    # 检查是否需要处理控制信息（有控制信息且选择了移除控制信息）
                    needs_cc_processing = remove_cc and has_cc_messages
                    
                    # 只有当不需要处理控制信息时，才跳过处理
                    if not needs_cc_processing:
                        print(f"文件不需要处理: BPM已匹配 ({original_bpm} BPM), 无控制信息需移除")
                        
                        # 初始化重叠处理文件保存标志
                        needs_overlap_file_save = False
                        
                        # 收集所有原始音符的绝对秒位置(仅用于信息返回)
                        note_positions = self._collect_note_positions(midi)
                        
                        # 检测音符重叠（即使文件不需要处理，也要检测重叠）
                        fix_overlap_status = "未处理"
                        overlap_status = "未检测"
                        overlap_details = ""
                        
                        if check_overlap:
                            print("\n===== 检测音符重叠 =====")
                            
                            # 检测是否为多轨道MIDI文件
                            track_count = len(midi.tracks)
                            has_multiple_note_tracks = sum(1 for track in midi.tracks if any(msg.type in ['note_on', 'note_off'] for msg in track)) > 1
                            
                            if has_multiple_note_tracks:
                                print(f"检测到多轨道MIDI文件（{track_count}个轨道）")
                                
                                if multitrack_overlap:
                                    # 用户明确启用了跨轨道处理，使用全局模式
                                    print("用户启用了跨轨道重叠处理，使用全局模式")
                                    overlap_result = self.detect_multitrack_overlaps(input_file)
                                    if overlap_result['has_overlap']:
                                        overlap_status = f"多轨全局重叠 ({overlap_result['total_overlaps']} 处)"
                                        overlap_details = f"同轨道: {overlap_result['same_track_overlaps']}, 跨轨道: {overlap_result['cross_track_overlaps']}"
                                        print(f"检测到全局重叠: 同轨道{overlap_result['same_track_overlaps']}个, 跨轨道{overlap_result['cross_track_overlaps']}个")
                                        
                                        # 重叠处理不受跳过匹配文件影响
                                        if fix_overlap:
                                            print("\n===== 处理全局多轨道重叠音符（跳过匹配文件时仍处理） =====")
                                            all_notes = overlap_result.get('all_notes', [])
                                            if all_notes:
                                                note_positions = self.fix_multitrack_overlapping_notes(
                                                    all_notes, fix_cross_track=True
                                                )
                                                fix_overlap_status = "已处理(全局模式)"
                                                print("全局多轨道重叠音符处理完成")
                                                # 跳过匹配但处理重叠时需要保存文件
                                                needs_overlap_file_save = True
                                            else:
                                                fix_overlap_status = "处理失败"
                                        else:
                                            fix_overlap_status = "未处理"
                                    else:
                                        overlap_status = "无重叠"
                                        overlap_details = ""
                                        fix_overlap_status = "无需处理"
                                        print("未检测到全局重叠")
                                    
                                    # 使用多轨道收集的音符位置
                                    if 'all_notes' in overlap_result and overlap_result['all_notes']:
                                        note_positions = overlap_result['all_notes']
                                else:
                                    # 多轨道MIDI文件，但用户未启用跨轨道处理，使用分轨道模式
                                    print("多轨道MIDI文件，使用分轨道模式（处理轨道内重叠）")
                                    overlap_result = self.detect_multitrack_overlaps(input_file)
                                    
                                    if overlap_result['has_overlap']:
                                        same_track_overlaps = overlap_result['same_track_overlaps']
                                        cross_track_overlaps = overlap_result['cross_track_overlaps']
                                        
                                        if same_track_overlaps > 0:
                                            overlap_status = f"轨道内重叠 ({same_track_overlaps} 处)"
                                            if cross_track_overlaps > 0:
                                                overlap_details = f"轨道内: {same_track_overlaps}, 跨轨道: {cross_track_overlaps}(正常，未处理)"
                                            else:
                                                overlap_details = f"轨道内: {same_track_overlaps}"
                                            print(f"检测到轨道内重叠: {same_track_overlaps}个, 跨轨道重叠: {cross_track_overlaps}个（正常，不处理）")
                                            
                                            # 重叠处理不受跳过匹配文件影响
                                            if fix_overlap:
                                                print("\n===== 处理轨道内重叠音符（跳过匹配文件时仍处理） =====")
                                                all_notes = overlap_result.get('all_notes', [])
                                                if all_notes:
                                                    note_positions = self.fix_multitrack_overlapping_notes(
                                                        all_notes, fix_cross_track=False
                                                    )
                                                    fix_overlap_status = "已处理(轨道内)"
                                                    print("轨道内重叠音符处理完成")
                                                    # 跳过匹配但处理重叠时需要保存文件
                                                    needs_overlap_file_save = True
                                                else:
                                                    fix_overlap_status = "处理失败"
                                            else:
                                                fix_overlap_status = "未处理"
                                        else:
                                            overlap_status = f"跨轨道重叠 ({cross_track_overlaps} 处, 正常)"
                                            overlap_details = f"跨轨道: {cross_track_overlaps}(正常，未处理)"
                                            print(f"只检测到跨轨道重叠: {cross_track_overlaps}个（正常，不处理）")
                                            fix_overlap_status = "无需处理"  # 只有跨轨道重叠时无需处理
                                    else:
                                        overlap_status = "无重叠"
                                        overlap_details = ""
                                        fix_overlap_status = "无需处理"
                                        print("未检测到任何重叠")
                                    
                                    # 使用多轨道收集的音符位置
                                    if 'all_notes' in overlap_result and overlap_result['all_notes']:
                                        note_positions = overlap_result['all_notes']
                            else:
                                # 单轨道MIDI文件，使用传统单轨道重叠检测和处理
                                print("检测到单轨道MIDI文件，使用传统模式")
                                overlap_result = self.detect_midi_overlaps(input_file)
                                if overlap_result['has_overlap']:
                                    overlap_status = f"存在重叠 ({len(overlap_result['overlaps'])} 处)"
                                    overlap_details = "\n".join(overlap_result['overlaps'])
                                    print(f"检测到重叠: {overlap_result['overlaps']}")
                                    
                                    # 重叠处理不受跳过匹配文件影响
                                    if fix_overlap:
                                        print("\n===== 处理单轨道重叠音符（跳过匹配文件时仍处理） =====")
                                        note_positions = self.fix_overlapping_notes(note_positions)
                                        fix_overlap_status = "已处理"
                                        print("单轨道重叠音符处理完成")
                                        # 跳过匹配但处理重叠时需要保存文件
                                        needs_overlap_file_save = True
                                    else:
                                        fix_overlap_status = "未处理"
                                else:
                                    overlap_status = "无重叠"
                                    overlap_details = ""
                                    fix_overlap_status = "无需处理"
                                    print("未检测到重叠")
                        
                        # 准备输出路径和文件保存逻辑
                        filename = os.path.basename(input_file)
                        output_path = os.path.join(output_dir, filename)
                        
                        # 如果重叠处理需要保存文件，则创建新文件
                        if 'needs_overlap_file_save' in locals() and needs_overlap_file_save:
                            print("\n===== 创建重叠处理后的MIDI文件 =====")
                            new_midi = self._create_new_midi_with_exact_timing(
                                midi, note_positions, target_bpm, remove_cc, set_velocity, False  # keep_original_tempo=False保持原始速度
                            )
                            new_midi.save(output_path)
                            print(f"已保存重叠处理后的文件: {output_path}")
                            status = "已处理（重叠）"
                        else:
                            # 仅检测或无需处理时不创建文件
                            if check_overlap and not fix_overlap:
                                status = "仅检测"
                            else:
                                status = "无需处理"
                            output_path = ""  # 无输出文件
                        
                        # 返回处理结果信息
                        tempo_info = []
                        for idx, (time_ticks, tempo, time_seconds, measure_beat) in enumerate(self.detailed_tempos):
                            tempo_info.append({
                                "id": idx + 1,
                                "time_ticks": time_ticks,
                                "time_seconds": time_seconds,
                                "measure_beat": measure_beat,
                                "tempo": tempo,
                                "bpm": self._tempo_to_bpm(tempo)
                            })
                        
                        # 设置正确的状态文本
                        # 音符力度状态：如果选中了统一音符力度，且力度不一致，则为"未处理"（表示需要处理但未处理）
                        if set_velocity:
                            if all_notes_match_velocity:
                                velocity_status = "无需处理"  # 音符力度已经一致
                            else:
                                velocity_status = "未处理"  # 需要处理但因为跳过匹配文件而未处理
                        else:
                            velocity_status = "未处理"  # 未选择统一力度
                        
                        # 控制信息状态：根据是否有控制信息决定
                        if remove_cc:
                            if has_cc_messages:
                                cc_status = "未处理"  # 有控制信息，但因为跳过匹配文件而未处理
                            else:
                                cc_status = "无需处理"  # 没有控制信息需要移除
                        else:
                            cc_status = "未处理"  # 未选择移除控制信息
                        
                        return {
                            "filename": filename,
                            "original_bpm": self._tempo_to_bpm(self.original_tempo) if self.original_tempo else "未知",
                            "target_bpm": target_bpm,
                            "velocity_modified": set_velocity,
                            "velocity_status": velocity_status,
                            "cc_removed": remove_cc,
                            "cc_status": cc_status,
                            "overlap_status": overlap_status,
                            "overlap_details": overlap_details,
                            "fix_overlap_status": fix_overlap_status,
                            "tempo_changes": tempo_info,
                            "note_count": len(note_positions),
                            "status": status,
                            "path": output_path,
                            "is_multi_tempo": has_multiple_tempos
                        }
                    else:
                        print(f"BPM匹配但需要移除控制信息，继续处理: {input_file}")
            
            # 收集所有原始音符的绝对秒位置
            print("\n===== 收集原始音符位置 =====")
            note_positions = self._collect_note_positions(midi)
            
            # 检测音符重叠
            fix_overlap_status = "未处理"
            if check_overlap:
                print("\n===== 检测音符重叠 =====")
                
                # 检测是否为多轨道MIDI文件
                track_count = len(midi.tracks)
                has_multiple_note_tracks = sum(1 for track in midi.tracks if any(msg.type in ['note_on', 'note_off'] for msg in track)) > 1
                
                if has_multiple_note_tracks:
                    print(f"检测到多轨道MIDI文件（{track_count}个轨道）")
                    
                    if multitrack_overlap:
                        # 用户明确启用了跨轨道处理，使用全局模式
                        print("用户启用了跨轨道重叠处理，使用全局模式")
                        overlap_result = self.detect_multitrack_overlaps(input_file)
                        if overlap_result['has_overlap']:
                            overlap_status = f"多轨全局重叠 ({overlap_result['total_overlaps']} 处)"
                            overlap_details = f"同轨道: {overlap_result['same_track_overlaps']}, 跨轨道: {overlap_result['cross_track_overlaps']}"
                            print(f"检测到全局重叠: 同轨道{overlap_result['same_track_overlaps']}个, 跨轨道{overlap_result['cross_track_overlaps']}个")
                            
                            # 处理全局重叠音符
                            if fix_overlap:
                                print("\n===== 处理全局多轨道重叠音符 =====")
                                all_notes = overlap_result.get('all_notes', [])
                                if all_notes:
                                    note_positions = self.fix_multitrack_overlapping_notes(
                                        all_notes, fix_cross_track=True
                                    )
                                    fix_overlap_status = "已处理(全局模式)"
                                    print("全局多轨道重叠音符处理完成")
                                else:
                                    fix_overlap_status = "处理失败"
                            else:
                                fix_overlap_status = "未处理"
                        else:
                            overlap_status = "无重叠"
                            overlap_details = ""
                            fix_overlap_status = "无需处理"
                            print("未检测到全局重叠")
                            
                            # 使用多轨道收集的音符位置
                            if 'all_notes' in overlap_result and overlap_result['all_notes']:
                                note_positions = overlap_result['all_notes']
                    else:
                        # 多轨道MIDI文件，但用户未启用跨轨道处理，使用分轨道模式
                        print("多轨道MIDI文件，使用分轨道模式（仅处理各轨道内部重叠）")
                        overlap_result = self.detect_multitrack_overlaps(input_file)
                        
                        if overlap_result['has_overlap']:
                            same_track_overlaps = overlap_result['same_track_overlaps']
                            cross_track_overlaps = overlap_result['cross_track_overlaps']
                            
                            if same_track_overlaps > 0:
                                overlap_status = f"轨道内重叠 ({same_track_overlaps} 处)"
                                if cross_track_overlaps > 0:
                                    overlap_details = f"轨道内: {same_track_overlaps}, 跨轨道: {cross_track_overlaps}(正常，未处理)"
                                else:
                                    overlap_details = f"轨道内: {same_track_overlaps}"
                                print(f"检测到轨道内重叠: {same_track_overlaps}个, 跨轨道重叠: {cross_track_overlaps}个（正常，不处理）")
                            else:
                                overlap_status = f"跨轨道重叠 ({cross_track_overlaps} 处, 正常)"
                                overlap_details = f"跨轨道: {cross_track_overlaps}(正常，未处理)"
                                print(f"只检测到跨轨道重叠: {cross_track_overlaps}个（正常，不处理）")
                            
                            # 处理轨道内重叠音符（仅处理同轨道内的重叠）
                            if fix_overlap and same_track_overlaps > 0:
                                print("\n===== 处理轨道内重叠音符 =====")
                                all_notes = overlap_result.get('all_notes', [])
                                if all_notes:
                                    note_positions = self.fix_multitrack_overlapping_notes(
                                        all_notes, fix_cross_track=False  # 仅处理轨道内重叠
                                    )
                                    fix_overlap_status = "已处理(轨道内)"
                                    print("轨道内重叠音符处理完成")
                                else:
                                    fix_overlap_status = "处理失败"
                            elif fix_overlap and same_track_overlaps == 0:
                                fix_overlap_status = "无需处理(无轨道内重叠)"
                                # 使用多轨道收集的音符位置
                                if 'all_notes' in overlap_result and overlap_result['all_notes']:
                                    note_positions = overlap_result['all_notes']
                            else:
                                fix_overlap_status = "未处理"
                                # 使用多轨道收集的音符位置
                                if 'all_notes' in overlap_result and overlap_result['all_notes']:
                                    note_positions = overlap_result['all_notes']
                        else:
                            overlap_status = "无重叠"
                            overlap_details = ""
                            fix_overlap_status = "无需处理"
                            print("未检测到任何重叠")
                            
                            # 使用多轨道收集的音符位置
                            if 'all_notes' in overlap_result and overlap_result['all_notes']:
                                note_positions = overlap_result['all_notes']
                else:
                    # 单轨道MIDI文件，使用传统单轨道重叠检测
                    print("检测到单轨道MIDI文件，使用传统模式")
                    overlap_result = self.detect_midi_overlaps(input_file)
                    if overlap_result['has_overlap']:
                        overlap_status = f"存在重叠 ({len(overlap_result['overlaps'])} 处)"
                        overlap_details = "\n".join(overlap_result['overlaps'])
                        print(f"检测到重叠: {overlap_result['overlaps']}")
                        
                        # 处理重叠音符
                        if fix_overlap:
                            print("\n===== 处理重叠音符 =====")
                            note_positions = self.fix_overlapping_notes(note_positions)
                            fix_overlap_status = "已处理"
                            print("重叠音符处理完成")
                        else:
                            fix_overlap_status = "未处理"
                    else:
                        overlap_status = "无重叠"
                        overlap_details = ""
                        fix_overlap_status = "无需处理"
                        print("未检测到重叠")
            else:
                overlap_details = ""
            
            # 判断是否需要创建新文件
            # 仅当以下情况之一成立时才创建新文件：
            # 1. BPM需要转换（keep_original_tempo=True 且 原始BPM != 目标BPM）
            # 2. 需要移除控制消息（remove_cc=True 且 存在控制消息）
            # 3. 需要设置音符力度（set_velocity=True 且 力度不一致）
            # 4. 需要处理重叠音符（fix_overlap=True 且 存在重叠）
            # 5. 强制处理模式（skip_matched=False，用户要求处理所有文件）
            
            # 检查是否需要BPM转换
            needs_bpm_conversion = (keep_original_tempo and 
                                  abs(self._tempo_to_bpm(self.original_tempo or 500000) - target_bpm) >= 0.1)
            
            # 检查是否需要移除控制消息
            needs_cc_removal = remove_cc and any(
                msg.type in ['control_change', 'pitchwheel', 'program_change', 
                           'aftertouch', 'polytouch', 'sysex']
                for track in midi.tracks for msg in track
            )
            
            # 检查是否需要设置音符力度
            needs_velocity_change = False
            if set_velocity:
                target_velocity = int(128 * velocity_percent / 100)
                for track in midi.tracks:
                    for msg in track:
                        if msg.type == 'note_on' and msg.velocity > 0:
                            if abs(msg.velocity - target_velocity) > 3:
                                needs_velocity_change = True
                                break
                    if needs_velocity_change:
                        break
            
            # 检查是否需要处理重叠音符
            needs_overlap_processing = fix_overlap and ("重叠" in overlap_status and overlap_status != "无重叠")
            
            # 强制处理模式：当用户关闭跳过匹配文件时，应该处理所有文件
            # 只要用户选择了任意一个处理选项，就应该强制处理
            has_any_processing_option = (keep_original_tempo or remove_cc or set_velocity or fix_overlap)
            force_processing = not skip_matched and has_any_processing_option
            
            # 判断是否需要创建新文件
            needs_file_output = (needs_bpm_conversion or needs_cc_removal or 
                               needs_velocity_change or needs_overlap_processing or 
                               force_processing)
            
            if needs_file_output:
                # 创建新的MIDI文件，保持音符的精确时间位置
                print("\n===== 创建新MIDI文件 =====")
                
                # 如果是强制处理模式，但实际上不需要任何处理，则直接复制文件
                if force_processing and not (needs_bpm_conversion or needs_cc_removal or 
                                           needs_velocity_change or needs_overlap_processing):
                    # 强制处理模式：复制原文件
                    import shutil
                    filename = os.path.basename(input_file)
                    output_path = os.path.join(output_dir, filename)
                    shutil.copy2(input_file, output_path)
                    print(f"强制处理模式：复制原文件到: {output_path}")
                    status = "已处理（强制）"
                else:
                    # 正常处理模式
                    new_midi = self._create_new_midi_with_exact_timing(
                        midi, note_positions, target_bpm, remove_cc, set_velocity, keep_original_tempo
                    )
                    
                    # 准备输出路径
                    filename = os.path.basename(input_file)
                    output_path = os.path.join(output_dir, filename)
                    
                    # 保存处理后的MIDI文件
                    new_midi.save(output_path)
                    print(f"已保存处理后的文件: {output_path}")
                    status = "成功"
            else:
                # 仅检测模式，不输出文件
                if check_overlap and not fix_overlap:
                    print("\n===== 仅检测模式，不输出文件 =====")
                    status = "仅检测"
                else:
                    print("\n===== 无需处理，不输出文件 =====")
                    status = "无需处理"
                
                # 使用原始文件路径作为参考
                filename = os.path.basename(input_file)
                output_path = ""  # 无输出文件
            
            # 返回处理结果信息
            tempo_info = []
            for idx, (time_ticks, tempo, time_seconds, measure_beat) in enumerate(self.detailed_tempos):
                tempo_info.append({
                    "id": idx + 1,
                    "time_ticks": time_ticks,
                    "time_seconds": time_seconds,
                    "measure_beat": measure_beat,
                    "tempo": tempo,
                    "bpm": self._tempo_to_bpm(tempo)
                })
            
            return {
                "filename": filename,
                "original_bpm": self._tempo_to_bpm(self.original_tempo) if self.original_tempo else "未知",
                "target_bpm": target_bpm,
                "velocity_modified": set_velocity,
                "velocity_status": velocity_status,
                "cc_removed": remove_cc,
                "cc_status": cc_status,
                "overlap_status": overlap_status,
                "overlap_details": overlap_details,
                "fix_overlap_status": fix_overlap_status,
                "tempo_changes": tempo_info,
                "note_count": len(note_positions),
                "status": status,
                "path": output_path,
                "is_multi_tempo": has_multiple_tempos
            }
            
        except Exception as e:
            import traceback
            print(f"处理错误: {str(e)}")
            print(traceback.format_exc())
            return {
                "filename": os.path.basename(input_file),
                "original_bpm": "未知",
                "target_bpm": target_bpm,
                "velocity_modified": set_velocity,
                "velocity_status": "处理失败",
                "cc_removed": remove_cc,
                "cc_status": "处理失败",
                "overlap_status": "检测失败",
                "overlap_details": "",
                "fix_overlap_status": "处理失败",
                "tempo_changes": [],
                "note_count": 0,
                "status": f"错误: {str(e)}",
                "path": "",
                "is_multi_tempo": False
            }
    
    def _create_timestamp_midi(self, ticks_per_beat: int) -> mido.MidiFile:
        """创建一个等间隔时间戳MIDI文件，用于测试和对比"""
        # 创建新的MIDI文件
        midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
        
        # 创建控制轨道
        control_track = mido.MidiTrack()
        midi.tracks.append(control_track)
        
        # 设置120BPM的速度
        tempo = 500000  # 120 BPM
        control_track.append(mido.MetaMessage('set_tempo', tempo=tempo, time=0))
        
        # 创建时间戳轨道
        timestamp_track = mido.MidiTrack()
        midi.tracks.append(timestamp_track)
        
        # 每秒添加一个C4音符（60）
        seconds_per_note = 1.0  # 每秒一个音符
        seconds_total = 60.0    # 总共60秒
        
        # 计算每个音符的tick间隔
        ticks_per_second = ticks_per_beat * 1000000 / tempo
        ticks_per_note = int(ticks_per_second * seconds_per_note)
        
        # 添加音符
        for i in range(int(seconds_total / seconds_per_note)):
            if i == 0:
                # 第一个音符从0开始
                timestamp_track.append(mido.Message('note_on', note=60, velocity=100, time=0))
                timestamp_track.append(mido.Message('note_off', note=60, velocity=0, time=10))
            else:
                # 后续音符间隔固定
                timestamp_track.append(mido.Message('note_on', note=60, velocity=100, time=ticks_per_note - 10))
                timestamp_track.append(mido.Message('note_off', note=60, velocity=0, time=10))
        
        return midi
    
    def _collect_note_positions(self, midi: mido.MidiFile) -> List[Dict[str, Any]]:
        """收集所有音符的绝对时间位置 - 修复版本"""
        note_positions = []
        
        for track_idx, track in enumerate(midi.tracks):
            absolute_time_ticks = 0
            # 使用栈来正确处理重叠的相同音符
            active_notes = {}  # {(note, channel): [stack of start_info]}
            
            for msg_idx, msg in enumerate(track):
                absolute_time_ticks += msg.time
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    # 记录音符开始
                    note_key = (msg.note, msg.channel)
                    if note_key not in active_notes:
                        active_notes[note_key] = []
                    
                    # 使用栈结构处理重叠的相同音符
                    active_notes[note_key].append({
                        'start_tick': absolute_time_ticks,
                        'velocity': msg.velocity
                    })
                
                elif (msg.type == 'note_off' or 
                      (msg.type == 'note_on' and msg.velocity == 0)):
                    # 找到音符结束
                    note_key = (msg.note, msg.channel)
                    if note_key in active_notes and active_notes[note_key]:
                        # 使用FIFO（先进先出）处理重叠音符 - 修复配对错误
                        start_info = active_notes[note_key].pop(0)
                        start_tick = start_info['start_tick']
                        velocity = start_info['velocity']
                        duration_ticks = absolute_time_ticks - start_tick
                        
                        # 使用高精度计算秒位置
                        start_seconds = self._calculate_absolute_time_with_tempo_changes_precise(
                            start_tick, self.tempo_changes, midi.ticks_per_beat
                        )
                        end_seconds = self._calculate_absolute_time_with_tempo_changes_precise(
                            absolute_time_ticks, self.tempo_changes, midi.ticks_per_beat
                        )
                        duration_seconds = end_seconds - start_seconds
                        
                        # 记录音符信息
                        note_positions.append({
                            'track': track_idx,
                            'note': msg.note,
                            'channel': msg.channel,
                            'velocity': velocity,
                            'start_tick': start_tick,
                            'end_tick': absolute_time_ticks,
                            'start_seconds': start_seconds,
                            'end_seconds': end_seconds,
                            'duration_ticks': duration_ticks,
                            'duration_seconds': duration_seconds
                        })
                        
                        # 如果这个音符的栈空了，删除key
                        if not active_notes[note_key]:
                            del active_notes[note_key]
        
        # 检查是否有未配对的note_on事件
        unmatched_count = sum(len(stack) for stack in active_notes.values())
        if unmatched_count > 0:
            print(f"警告: 有 {unmatched_count} 个note_on事件没有找到对应的note_off事件")
        
        # 按开始时间排序
        note_positions.sort(key=lambda x: x['start_seconds'])
        
        # 打印首个音符信息
        if note_positions:
            first_note = note_positions[0]
            print(f"首个音符: {first_note['note']} 在轨道 {first_note['track']+1}, "
                  f"通道 {first_note['channel']+1}, 时间 {first_note['start_seconds']:.6f} 秒, "
                  f"{first_note['start_tick']} ticks, 持续 {first_note['duration_seconds']:.6f} 秒")
            
            # 如果有多个音符，也打印第二个
            if len(note_positions) > 1:
                second_note = note_positions[1]
                print(f"第二个音符: {second_note['note']} 在轨道 {second_note['track']+1}, "
                      f"通道 {second_note['channel']+1}, 时间 {second_note['start_seconds']:.6f} 秒, "
                      f"{second_note['start_tick']} ticks, 持续 {second_note['duration_seconds']:.6f} 秒")
        
        return note_positions
    
    def _create_new_midi_with_exact_timing(self, 
                                        orig_midi: mido.MidiFile, 
                                        note_positions: List[Dict[str, Any]],
                                        target_bpm: float,
                                        remove_cc: bool,
                                        set_velocity: bool,
                                        keep_original_tempo: bool = False) -> mido.MidiFile:
        """
        创建新的MIDI文件，保持音符的精确时间位置
        
        Args:
            orig_midi: 原始MIDI文件
            note_positions: 音符位置列表
            target_bpm: 目标BPM
            remove_cc: 是否删除控制消息
            set_velocity: 是否设置固定力度
            keep_original_tempo: 是否启用MIDI速度转换（True=启用转换，False=保持原始速度）
            
        Returns:
            新的MIDI文件
        """
        # 创建新的MIDI文件
        new_midi = mido.MidiFile(type=orig_midi.type, ticks_per_beat=orig_midi.ticks_per_beat)
        
        # 根据是否启用速度转换决定目标tempo
        # keep_original_tempo现在表示是否启用速度转换（True=启用转换，False=保持原始速度）
        if keep_original_tempo:
            target_tempo = self._bpm_to_tempo(target_bpm)
            print(f"设置目标速度: {target_bpm:.2f} BPM")
        else:
            target_tempo = self.original_tempo if self.original_tempo else self._bpm_to_tempo(target_bpm)
            print(f"保持原始速度: {self._tempo_to_bpm(target_tempo):.2f} BPM")
        
        # 计算实际力度值 (将百分比正确转换为MIDI力度值，范围1-127)
        velocity_value = min(127, max(1, int(127 * self.velocity_percent / 100)))
        print(f"设置音符力度为: {velocity_value} ({self.velocity_percent}%)")
        
        # 创建新的轨道
        for i in range(len(orig_midi.tracks)):
            new_track = mido.MidiTrack()
            new_midi.tracks.append(new_track)
            
            # 如果是第一个轨道，添加tempo消息
            if i == 0:
                new_track.append(mido.MetaMessage('set_tempo', tempo=target_tempo, time=0))
        
        # 先收集每个轨道的所有事件
        track_events = [[] for _ in range(len(orig_midi.tracks))]
        
        for track_idx, track in enumerate(orig_midi.tracks):
            absolute_ticks = 0
            for msg in track:
                absolute_ticks += msg.time
                
                # 跳过音符事件（这些会通过note_positions重新添加）
                if msg.type in ['note_on', 'note_off']:
                    continue
                    
                # 如果勾选删除CC，跳过控制器、程序改变等控制类事件
                if remove_cc and msg.type in ['control_change', 'pitchwheel', 'program_change', 
                                            'aftertouch', 'polytouch', 'sysex']:
                    continue
                    
                # 跳过速度事件（我们已经设置了新的速度）
                if msg.type == 'set_tempo':
                    continue
                    
                # 跳过标记事件
                if msg.type in ['marker', 'text', 'cue_marker', 'lyrics']:
                    continue
                
                # 计算事件的绝对秒位置
                absolute_seconds = self._calculate_absolute_time_with_tempo_changes(
                    absolute_ticks, self.tempo_changes, orig_midi.ticks_per_beat
                )
                
                # 对于CC控制信息，需要转换时间位置到新的速度
                if not remove_cc and msg.type in ['control_change', 'pitchwheel', 'program_change', 
                                                'aftertouch', 'polytouch', 'sysex']:
                    # 计算新的tick位置
                    new_ticks = self._seconds_to_ticks_precise(absolute_seconds, target_tempo, orig_midi.ticks_per_beat)
                    
                    # 保存控制事件和转换后的时间位置
                    track_events[track_idx].append({
                        'msg': msg,
                        'absolute_ticks': new_ticks,
                        'absolute_seconds': absolute_seconds
                    })
                else:
                    # 对于其他事件，保持原始时间位置
                    track_events[track_idx].append({
                        'msg': msg,
                        'absolute_ticks': absolute_ticks,
                        'absolute_seconds': absolute_seconds
                    })
        
        # 按轨道处理所有音符
        for note in note_positions:
            track_idx = note['track']
            
            # 计算新的tick位置，使用高精度时间计算
            new_start_ticks = self._seconds_to_ticks_precise(note['start_seconds'], target_tempo, orig_midi.ticks_per_beat)
            new_end_ticks = self._seconds_to_ticks_precise(note['end_seconds'], target_tempo, orig_midi.ticks_per_beat)
            
            # 创建音符开始事件
            note_on = mido.Message('note_on', 
                                channel=note['channel'],
                                note=note['note'], 
                                velocity=velocity_value if set_velocity else note['velocity'],
                                time=0)  # 稍后我们会计算正确的delta时间
            
            # 创建音符结束事件
            note_off = mido.Message('note_off',
                                 channel=note['channel'],
                                 note=note['note'],
                                 velocity=0,
                                 time=0)  # 稍后我们会计算正确的delta时间
            
            # 将音符事件添加到相应的轨道
            track_events[track_idx].append({
                'msg': note_on,
                'absolute_ticks': new_start_ticks,
                'absolute_seconds': note['start_seconds']
            })
            
            track_events[track_idx].append({
                'msg': note_off,
                'absolute_ticks': new_end_ticks,
                'absolute_seconds': note['end_seconds']
            })
        
        # 按时间顺序排序并计算delta时间
        for track_idx, events in enumerate(track_events):
            events.sort(key=lambda x: x['absolute_ticks'])
            
            last_tick = 0
            for event in events:
                # 计算delta时间
                delta_ticks = event['absolute_ticks'] - last_tick
                last_tick = event['absolute_ticks']
                
                # 更新事件的时间
                new_msg = event['msg'].copy(time=delta_ticks)
                
                # 添加到新轨道
                new_midi.tracks[track_idx].append(new_msg)
        
        return new_midi
    
    def _calculate_measure_beat(self, ticks, ticks_per_beat):
        """计算小节:拍位置（假设4/4拍）"""
        beats = ticks / ticks_per_beat
        measures = int(beats / 4)  # 假设4/4拍
        beat_in_measure = beats % 4
        return f"{measures+1}:{beat_in_measure+1:.2f}"
    
    def _analyze_tempo(self, midi: mido.MidiFile) -> None:
        """
        分析MIDI文件中的速度信息
        直接读取MIDI中的tempo元信息，不进行任何计算或检测
        收集所有速度变化点的绝对时间和速度值
        """
        self.tempo_changes = []
        self.original_tempo = None
        self.detailed_tempos = []
        
        # 首先收集所有轨道中的所有tempo变化
        all_tempo_events = []
        
        # 收集所有音符，用于验证
        all_note_events = []
        
        print(f"MIDI格式: {midi.type}, Ticks per beat: {midi.ticks_per_beat}")
        
        # 如果是FORMAT 1的MIDI，第一轨通常是tempo轨
        # 如果是FORMAT 0，所有事件在同一轨
        for i, track in enumerate(midi.tracks):
            absolute_time = 0  # 累积tick时间
            
            print(f"\n轨道 {i+1} ({len(track)} 个事件):")
            tempo_count_in_track = 0
            
            for msg in track:
                absolute_time += msg.time
                
                if msg.type == 'set_tempo':
                    tempo_count_in_track += 1
                    # 记录tempo变化的绝对tick位置和速度
                    all_tempo_events.append((absolute_time, msg.tempo, i))
                    print(f"  速度变化 {tempo_count_in_track}: 位置 {absolute_time} ticks, "
                          f"速度: {60000000/msg.tempo:.2f} BPM ({msg.tempo} μs/beat), "
                          f"小节位置: {self._calculate_measure_beat(absolute_time, midi.ticks_per_beat)}")
                
                elif msg.type == 'note_on' and msg.velocity > 0:
                    # 记录音符事件用于验证
                    all_note_events.append((absolute_time, i, msg))
        
        # 按绝对时间排序所有tempo变化
        all_tempo_events.sort(key=lambda x: x[0])
        
        print(f"\n检测到总共 {len(all_tempo_events)} 个速度变化点:")
        
        # 如果有tempo变化，计算每个变化点的秒数位置
        if all_tempo_events:
            # 设置第一个tempo为原始速度
            self.original_tempo = all_tempo_events[0][1]
            
            # 确保第一个tempo变化的时间为0
            if all_tempo_events[0][0] > 0:
                print(f"首个tempo变化不在0点，在 {all_tempo_events[0][0]} ticks，添加初始tempo事件")
                first_tempo = all_tempo_events[0][1]
                self.tempo_changes = [(0, first_tempo)] + [(t[0], t[1]) for t in all_tempo_events]  # 添加0时刻的速度
                all_tempo_events.insert(0, (0, first_tempo, -1))  # -1表示这是程序添加的
            else:
                self.tempo_changes = [(t[0], t[1]) for t in all_tempo_events]
            
            # 计算每个tempo变化点的绝对秒数位置
            calculated_tempos = []
            for idx, (tick_pos, tempo, track_idx) in enumerate(all_tempo_events):
                seconds = self._calculate_absolute_time_with_tempo_changes(
                    tick_pos, 
                    [(t[0], t[1]) for t in all_tempo_events[:idx+1]],  # 转换为 (ticks, tempo) 对
                    midi.ticks_per_beat
                )
                measure_beat = self._calculate_measure_beat(tick_pos, midi.ticks_per_beat)
                calculated_tempos.append((tick_pos, tempo, seconds, measure_beat))
                print(f"  {idx+1}. 时间位置: {tick_pos} ticks ({seconds:.3f} 秒), "
                      f"小节位置: {measure_beat}, "
                      f"速度: {self._tempo_to_bpm(tempo):.2f} BPM ({tempo} μs/beat), "
                      f"轨道: {track_idx+1}")
            
            self.detailed_tempos = calculated_tempos
        else:
            # 如果没有找到速度信息，使用MIDI默认速度（500000微秒/拍，相当于120 BPM）
            self.original_tempo = 500000
            self.tempo_changes = [(0, 500000)]  # 添加一个初始点
            self.detailed_tempos = [(0, 500000, 0.0, "1:1.00")]
            print(f"警告: 未找到速度信息，使用默认值 120 BPM")
        
        # 验证音符位置
        if all_note_events:
            all_note_events.sort(key=lambda x: x[0])
            first_note = all_note_events[0]
            seconds = self._calculate_absolute_time_with_tempo_changes(
                first_note[0], 
                self.tempo_changes,
                midi.ticks_per_beat
            )
            measure_beat = self._calculate_measure_beat(first_note[0], midi.ticks_per_beat)
            print(f"\n首个音符在 {first_note[0]} ticks ({seconds:.3f} 秒), "
                  f"小节位置: {measure_beat}, 轨道 {first_note[1]+1}")
            
    def _tempo_to_bpm(self, tempo: int) -> float:
        """将微秒/拍转换为BPM"""
        if tempo <= 0:
            return 120.0  # 防止除零错误
        return round(60000000 / tempo, 2)
    
    def _bpm_to_tempo(self, bpm: float) -> int:
        """将BPM转换为微秒/拍"""
        if bpm <= 0:
            return 500000  # 防止除零错误
        return int(60000000 / bpm)
        
    def _ticks_to_seconds(self, ticks: int, tempo: int, ticks_per_beat: int) -> float:
        """
        将MIDI ticks转换为秒
        
        Args:
            ticks: MIDI ticks
            tempo: 微秒/拍
            ticks_per_beat: 每拍的ticks数
            
        Returns:
            秒
        """
        return (ticks * tempo) / (ticks_per_beat * 1000000)
    
    def _seconds_to_ticks(self, seconds: float, tempo: int, ticks_per_beat: int) -> int:
        """
        将秒转换为MIDI ticks
        
        Args:
            seconds: 秒
            tempo: 微秒/拍
            ticks_per_beat: 每拍的ticks数
            
        Returns:
            MIDI ticks
        """
        return int((seconds * 1000000 * ticks_per_beat) / tempo)
        
    def _seconds_to_ticks_precise(self, seconds: float, tempo: int, ticks_per_beat: int) -> int:
        """
        将秒转换为MIDI ticks，使用更高精度的计算
        
        Args:
            seconds: 秒
            tempo: 微秒/拍
            ticks_per_beat: 每拍的ticks数
            
        Returns:
            MIDI ticks
        """
        # 使用高精度计算，避免浮点数舍入错误
        seconds_per_beat = tempo / 1000000.0
        beats = seconds / seconds_per_beat
        return round(beats * ticks_per_beat)
    
    def _calculate_absolute_time_with_tempo_changes(self, absolute_ticks: int, tempo_changes: List[Tuple[int, int]], ticks_per_beat: int) -> float:
        """
        计算考虑所有tempo变化的绝对时间（秒）
        
        Args:
            absolute_ticks: 事件的绝对tick位置
            tempo_changes: 所有速度变化的列表，按时间排序 [(tick_pos, tempo),...]
            ticks_per_beat: 每拍的ticks数
            
        Returns:
            绝对时间（秒）
        """
        if not tempo_changes:
            return 0.0
            
        # 确保tempo_changes按tick位置排序
        sorted_tempo_changes = sorted(tempo_changes, key=lambda x: x[0])
        
        # 总时间
        total_seconds = 0.0
        last_tick_pos = 0
        last_tempo = sorted_tempo_changes[0][1]  # 使用第一个速度
        
        if self.debug_mode and absolute_ticks > 0 and absolute_ticks % 10000 == 0:
            print(f"\n计算 {absolute_ticks} ticks 的绝对时间:")
            print(f"  起始tempo: {self._tempo_to_bpm(last_tempo):.2f} BPM ({last_tempo} μs/beat)")
        
        # 遍历所有tempo变化
        for tick_pos, tempo in sorted_tempo_changes:
            # 如果事件在当前tempo变化点之前
            if absolute_ticks <= tick_pos:
                # 添加从上一个tempo变化点到事件位置的时间
                tick_duration = absolute_ticks - last_tick_pos
                time_segment = self._ticks_to_seconds(tick_duration, last_tempo, ticks_per_beat)
                total_seconds += time_segment
                
                if self.debug_mode and absolute_ticks > 0 and absolute_ticks % 10000 == 0:
                    print(f"  事件在 {tick_pos} ticks 之前，当前位置 {absolute_ticks} ticks")
                    print(f"  从 {last_tick_pos} 到 {absolute_ticks} = {tick_duration} ticks @ {self._tempo_to_bpm(last_tempo):.2f} BPM = {time_segment:.6f} 秒")
                    print(f"  总时间: {total_seconds:.6f} 秒")
                
                return total_seconds
            
            # 否则，添加从上一个tempo变化点到当前变化点的时间
            tick_duration = tick_pos - last_tick_pos
            time_segment = self._ticks_to_seconds(tick_duration, last_tempo, ticks_per_beat)
            total_seconds += time_segment
            
            if self.debug_mode and absolute_ticks > 0 and absolute_ticks % 10000 == 0:
                print(f"  从 {last_tick_pos} 到 {tick_pos} = {tick_duration} ticks @ {self._tempo_to_bpm(last_tempo):.2f} BPM = {time_segment:.6f} 秒")
                print(f"  累计时间: {total_seconds:.6f} 秒")
                print(f"  速度变化为 {self._tempo_to_bpm(tempo):.2f} BPM ({tempo} μs/beat)")
            
            # 更新上一个位置和tempo
            last_tick_pos = tick_pos
            last_tempo = tempo
        
        # 如果事件在所有tempo变化之后
        tick_duration = absolute_ticks - last_tick_pos
        time_segment = self._ticks_to_seconds(tick_duration, last_tempo, ticks_per_beat)
        total_seconds += time_segment
        
        if self.debug_mode and absolute_ticks > 0 and absolute_ticks % 10000 == 0:
            print(f"  事件在所有tempo变化之后，最后位置 {last_tick_pos} ticks")
            print(f"  从 {last_tick_pos} 到 {absolute_ticks} = {tick_duration} ticks @ {self._tempo_to_bpm(last_tempo):.2f} BPM = {time_segment:.6f} 秒")
            print(f"  总时间: {total_seconds:.6f} 秒")
        
        return total_seconds
    
    def _calculate_absolute_time_with_tempo_changes_precise(self, absolute_ticks: int, tempo_changes: List[Tuple[int, int]], ticks_per_beat: int) -> float:
        """
        计算考虑所有tempo变化的绝对时间（秒），使用高精度算法
        
        Args:
            absolute_ticks: 事件的绝对tick位置
            tempo_changes: 所有速度变化的列表，按时间排序 [(tick_pos, tempo),...]
            ticks_per_beat: 每拍的ticks数
            
        Returns:
            绝对时间（秒）
        """
        # 基本上与原方法相同，但使用更高精度的计算
        if not tempo_changes:
            return 0.0
        
        # 确保tempo_changes按tick位置排序
        sorted_tempo_changes = sorted(tempo_changes, key=lambda x: x[0])
        
        # 总时间
        total_seconds = 0.0
        last_tick_pos = 0
        last_tempo = sorted_tempo_changes[0][1]  # 使用第一个速度
        
        # 遍历所有tempo变化
        for tick_pos, tempo in sorted_tempo_changes:
            # 如果事件在当前tempo变化点之前
            if absolute_ticks <= tick_pos:
                # 添加从上一个tempo变化点到事件位置的时间
                tick_duration = absolute_ticks - last_tick_pos
                # 使用高精度计算
                seconds_per_beat = last_tempo / 1000000.0
                beats = tick_duration / ticks_per_beat
                time_segment = beats * seconds_per_beat
                total_seconds += time_segment
                return total_seconds
            
            # 否则，添加从上一个tempo变化点到当前变化点的时间
            tick_duration = tick_pos - last_tick_pos
            # 使用高精度计算
            seconds_per_beat = last_tempo / 1000000.0
            beats = tick_duration / ticks_per_beat
            time_segment = beats * seconds_per_beat
            total_seconds += time_segment
            
            # 更新上一个位置和tempo
            last_tick_pos = tick_pos
            last_tempo = tempo
        
        # 如果事件在所有tempo变化之后
        tick_duration = absolute_ticks - last_tick_pos
        # 使用高精度计算
        seconds_per_beat = last_tempo / 1000000.0
        beats = tick_duration / ticks_per_beat
        time_segment = beats * seconds_per_beat
        total_seconds += time_segment
        
        return total_seconds
    
    def process_directory(self, 
                         input_dir: str, 
                         output_dir: str, 
                         target_bpm: float = 120.0, 
                         remove_cc: bool = True, 
                         set_velocity: bool = True,
                         velocity_percent: int = 80,
                         skip_matched: bool = True,
                         keep_original_tempo: bool = True,
                         check_overlap: bool = False,
                         fix_overlap: bool = False,
                         multitrack_overlap: bool = False) -> List[Dict[str, Any]]:
        """
        批量处理目录中的所有MIDI文件
        
        Args:
            input_dir: 输入目录
            output_dir: 输出目录
            target_bpm: 目标BPM
            remove_cc: 是否删除控制消息
            set_velocity: 是否设置固定力度
            velocity_percent: 力度百分比(1-100)
            skip_matched: 如果文件已匹配条件则跳过处理
            keep_original_tempo: 是否启用MIDI速度转换（True=启用转换，False=保持原始速度）
            check_overlap: 是否检测音符重叠
            fix_overlap: 是否处理重叠音符
            multitrack_overlap: 是否处理跨轨道重叠
            
        Returns:
            包含所有处理结果的列表
        """
        results = []
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 遍历目录中的所有文件
        for root, _, files in os.walk(input_dir):
            for file in files:
                if file.lower().endswith(('.mid', '.midi')):
                    input_path = os.path.join(root, file)
                    
                    # 计算相对路径以保持目录结构
                    rel_path = os.path.relpath(root, input_dir)
                    if rel_path != '.':
                        target_dir = os.path.join(output_dir, rel_path)
                        os.makedirs(target_dir, exist_ok=True)
                    else:
                        target_dir = output_dir
                    
                    # 处理文件并收集结果
                    result = self.process_file(
                        input_path, 
                        target_dir, 
                        target_bpm, 
                        remove_cc, 
                        set_velocity,
                        velocity_percent,
                        skip_matched,
                        keep_original_tempo,
                        check_overlap,
                        fix_overlap,
                        multitrack_overlap
                    )
                    results.append(result)
        
        return results
    
    def detect_midi_overlaps(self, midi_path: str) -> Dict[str, Any]:
        """
        检测MIDI文件中的音符重叠
        
        Args:
            midi_path: MIDI文件路径
            
        Returns:
            包含重叠检测结果的字典
        """
        try:
            mid = mido.MidiFile(midi_path)
            overlaps = []
            tempo = 500000  # 默认 tempo
            
            # 获取第一个tempo信息
            for msg in mid:
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                    break

            for track_idx, track in enumerate(mid.tracks):
                current_time = 0
                active_notes = []

                for msg in track:
                    current_time += msg.time

                    if msg.type == 'note_on' and msg.velocity > 0:
                        active_notes.append({
                            'channel': msg.channel,
                            'note': msg.note,
                            'start': current_time,
                            'end': None
                        })
                    elif (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0):
                        for note in active_notes:
                            if note['channel'] == msg.channel and note['note'] == msg.note and note['end'] is None:
                                note['end'] = current_time
                                break

                for i in range(len(active_notes)):
                    for j in range(i + 1, len(active_notes)):
                        note1 = active_notes[i]
                        note2 = active_notes[j]

                        if note1['end'] is not None and note2['end'] is not None:
                            if note1['start'] < note2['end'] and note2['start'] < note1['end']:
                                overlap_start = max(note1['start'], note2['start'])
                                overlap_end = min(note1['end'], note2['end'])
                                formatted_overlap_start = self._format_time(overlap_start, mid.ticks_per_beat, tempo)
                                formatted_overlap_end = self._format_time(overlap_end, mid.ticks_per_beat, tempo)
                                overlap_info = f"{formatted_overlap_start} - {formatted_overlap_end}"
                                if overlap_info not in overlaps:
                                    overlaps.append(overlap_info)

            return {
                'has_overlap': bool(overlaps),
                'overlaps': overlaps
            }

        except Exception as e:
            return {
                'has_overlap': False,
                'overlaps': [f"处理文件时出错: {str(e)}"]
            }
    
    def _format_time(self, ticks: int, ticks_per_beat: int, tempo: int) -> str:
        """
        将MIDI ticks转换为时间格式
        
        Args:
            ticks: MIDI ticks
            ticks_per_beat: 每拍的ticks数
            tempo: MIDI tempo (微秒/拍)
            
        Returns:
            格式化的时间字符串 (MM:SS.ms)
        """
        tick_per_second = tempo / (ticks_per_beat * 1000000)
        total_seconds = ticks * tick_per_second
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds % 1) * 100)
        return f"{minutes:02}:{seconds:02}.{milliseconds:02}"
    
    def fix_overlapping_notes(self, note_positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        处理重叠的音符
        
        处理规则：
        1. 完全重叠的音符仅保留一个，优先保留更早开始的音符
        2. 前后交叉重叠时，从前一个音符中删除重叠部分，保留后一个音符的完整起始点
        3. 删除持续时间小于1ms的音符
        
        Args:
            note_positions: 音符位置列表
            
        Returns:
            处理后的音符位置列表
        """
        if not note_positions:
            return note_positions
        
        print(f"开始处理 {len(note_positions)} 个音符")
        
        # 按通道分组处理
        channel_groups = {}
        for note in note_positions:
            channel = note['channel']
            if channel not in channel_groups:
                channel_groups[channel] = []
            channel_groups[channel].append(note)
        
        fixed_notes = []
        
        for channel, notes in channel_groups.items():
            print(f"处理通道 {channel}: {len(notes)} 个音符")
            
            # 按开始时间排序
            sorted_notes = sorted(notes, key=lambda x: x['start_seconds'])
            
            # 使用扫描线算法处理重叠
            channel_fixed = self._fix_channel_overlaps(sorted_notes)
            fixed_notes.extend(channel_fixed)
        
        print(f"处理完成：{len(note_positions)} 个音符 -> {len(fixed_notes)} 个音符")
        return fixed_notes

    def collect_multitrack_note_positions(self, midi: mido.MidiFile) -> List[Dict[str, Any]]:
        """
        收集多轨MIDI文件中所有音符的位置信息
        
        Args:
            midi: MIDI文件对象
            
        Returns:
            包含所有轨道音符位置信息的列表，每个音符都标记了原始轨道信息
        """
        all_notes = []
        
        for track_idx, track in enumerate(midi.tracks):
            absolute_time_ticks = 0
            # 使用栈来正确处理重叠的相同音符
            active_notes = {}  # {(note, channel): [stack of start_info]}
            
            for msg_idx, msg in enumerate(track):
                absolute_time_ticks += msg.time
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    # 记录音符开始
                    note_key = (msg.note, msg.channel)
                    if note_key not in active_notes:
                        active_notes[note_key] = []
                    
                    # 使用栈结构处理重叠的相同音符
                    active_notes[note_key].append({
                        'start_tick': absolute_time_ticks,
                        'velocity': msg.velocity
                    })
                
                elif (msg.type == 'note_off' or 
                      (msg.type == 'note_on' and msg.velocity == 0)):
                    # 找到音符结束
                    note_key = (msg.note, msg.channel)
                    if note_key in active_notes and active_notes[note_key]:
                        # 使用FIFO（先进先出）处理重叠音符
                        start_info = active_notes[note_key].pop(0)
                        start_tick = start_info['start_tick']
                        velocity = start_info['velocity']
                        duration_ticks = absolute_time_ticks - start_tick
                        
                        # 使用高精度计算秒位置
                        start_seconds = self._calculate_absolute_time_with_tempo_changes_precise(
                            start_tick, self.tempo_changes, midi.ticks_per_beat
                        )
                        end_seconds = self._calculate_absolute_time_with_tempo_changes_precise(
                            absolute_time_ticks, self.tempo_changes, midi.ticks_per_beat
                        )
                        duration_seconds = end_seconds - start_seconds
                        
                        # 记录音符信息，包含原始轨道信息
                        note_info = {
                            'track': track_idx,
                            'original_track': track_idx,  # 保存原始轨道索引
                            'note': msg.note,
                            'channel': msg.channel,
                            'velocity': velocity,
                            'start_tick': start_tick,
                            'end_tick': absolute_time_ticks,
                            'start_seconds': start_seconds,
                            'end_seconds': end_seconds,
                            'duration_ticks': duration_ticks,
                            'duration_seconds': duration_seconds
                        }
                        
                        all_notes.append(note_info)
                        
                        # 如果这个音符的栈空了，删除key
                        if not active_notes[note_key]:
                            del active_notes[note_key]
        
        # 检查是否有未配对的note_on事件
        total_unmatched = 0
        for track_idx, track in enumerate(midi.tracks):
            # 重新计算该轨道的未配对事件
            track_unmatched = 0
            absolute_time_ticks = 0
            active_notes = {}
            
            for msg in track:
                absolute_time_ticks += msg.time
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    note_key = (msg.note, msg.channel)
                    if note_key not in active_notes:
                        active_notes[note_key] = []
                    active_notes[note_key].append(absolute_time_ticks)
                
                elif (msg.type == 'note_off' or 
                      (msg.type == 'note_on' and msg.velocity == 0)):
                    note_key = (msg.note, msg.channel)
                    if note_key in active_notes and active_notes[note_key]:
                        active_notes[note_key].pop(0)
                        if not active_notes[note_key]:
                            del active_notes[note_key]
            
            track_unmatched = sum(len(stack) for stack in active_notes.values())
            total_unmatched += track_unmatched
            
            if track_unmatched > 0:
                print(f"警告: 轨道{track_idx+1}有 {track_unmatched} 个note_on事件没有找到对应的note_off事件")
        
        if total_unmatched > 0:
            print(f"总计警告: 有 {total_unmatched} 个note_on事件没有找到对应的note_off事件")
        
        # 按开始时间排序
        all_notes.sort(key=lambda x: x['start_seconds'])
        
        print(f"多轨MIDI分析完成: 共收集到 {len(all_notes)} 个音符，分布在 {len(midi.tracks)} 个轨道中")
        
        return all_notes

    def detect_multitrack_overlaps(self, midi_file_path: str) -> Dict[str, Any]:
        """
        检测多轨MIDI文件中的重叠情况
        
        Args:
            midi_file_path: MIDI文件路径
            
        Returns:
            包含重叠检测结果的字典
        """
        try:
            # 加载MIDI文件
            midi = mido.MidiFile(midi_file_path)
            self._analyze_tempo(midi)
            
            # 收集所有轨道的音符
            all_notes = self.collect_multitrack_note_positions(midi)
            
            if not all_notes:
                return {
                    'has_overlap': False,
                    'total_overlaps': 0,
                    'same_track_overlaps': 0,
                    'cross_track_overlaps': 0,
                    'overlaps': [],
                    'overlap_details': []
                }
            
            # 检测重叠
            overlaps = []
            overlap_details = []
            
            print(f"开始检测 {len(all_notes)} 个音符之间的重叠...")
            
            for i in range(len(all_notes)):
                for j in range(i + 1, len(all_notes)):
                    note1 = all_notes[i]
                    note2 = all_notes[j]
                    
                    # 检查时间重叠
                    if (note1['start_seconds'] < note2['end_seconds'] and 
                        note2['start_seconds'] < note1['end_seconds']):
                        
                        overlap_start = max(note1['start_seconds'], note2['start_seconds'])
                        overlap_end = min(note1['end_seconds'], note2['end_seconds'])
                        overlap_duration = overlap_end - overlap_start
                        
                        # 格式化时间
                        start1 = f"{int(note1['start_seconds']//60):02d}:{int(note1['start_seconds']%60):02d}.{int((note1['start_seconds']%1)*1000):03d}"
                        end1 = f"{int(note1['end_seconds']//60):02d}:{int(note1['end_seconds']%60):02d}.{int((note1['end_seconds']%1)*1000):03d}"
                        start2 = f"{int(note2['start_seconds']//60):02d}:{int(note2['start_seconds']%60):02d}.{int((note2['start_seconds']%1)*1000):03d}"
                        end2 = f"{int(note2['end_seconds']//60):02d}:{int(note2['end_seconds']%60):02d}.{int((note2['end_seconds']%1)*1000):03d}"
                        overlap_start_fmt = f"{int(overlap_start//60):02d}:{int(overlap_start%60):02d}.{int((overlap_start%1)*1000):03d}"
                        overlap_end_fmt = f"{int(overlap_end//60):02d}:{int(overlap_end%60):02d}.{int((overlap_end%1)*1000):03d}"
                        
                        # 判断重叠类型
                        same_track = note1['original_track'] == note2['original_track']
                        same_note = note1['note'] == note2['note']
                        same_channel = note1['channel'] == note2['channel']
                        
                        track_info = f"轨道{note1['original_track']+1}" if same_track else f"轨道{note1['original_track']+1} vs 轨道{note2['original_track']+1}"
                        overlap_type = "同音符" if same_note else "不同音符"
                        
                        overlap_desc = (
                            f"{track_info}: "
                            f"音符{note1['note']} [{start1}-{end1}] vs "
                            f"音符{note2['note']} [{start2}-{end2}] "
                            f"重叠[{overlap_start_fmt}-{overlap_end_fmt}] "
                            f"持续{overlap_duration:.3f}s ({overlap_type})"
                        )
                        
                        overlaps.append(overlap_desc)
                        
                        # 详细重叠信息
                        overlap_detail = {
                            'note1': note1,
                            'note2': note2,
                            'overlap_start': overlap_start,
                            'overlap_end': overlap_end,
                            'overlap_duration': overlap_duration,
                            'same_track': same_track,
                            'same_note': same_note,
                            'same_channel': same_channel,
                            'track_info': track_info,
                            'overlap_type': overlap_type,
                            'description': overlap_desc
                        }
                        
                        overlap_details.append(overlap_detail)
            
            # 统计不同类型的重叠
            same_track_count = len([o for o in overlap_details if o['same_track']])
            cross_track_count = len([o for o in overlap_details if not o['same_track']])
            
            print(f"重叠检测完成: 共发现 {len(overlaps)} 个重叠")
            print(f"  同轨道重叠: {same_track_count} 个")
            print(f"  跨轨道重叠: {cross_track_count} 个")
            
            return {
                'has_overlap': len(overlaps) > 0,
                'total_overlaps': len(overlaps),
                'same_track_overlaps': same_track_count,
                'cross_track_overlaps': cross_track_count,
                'overlaps': overlaps,
                'overlap_details': overlap_details,
                'all_notes': all_notes
            }
            
        except Exception as e:
            print(f"多轨重叠检测出错: {e}")
            import traceback
            traceback.print_exc()
            return {
                'has_overlap': False,
                'total_overlaps': 0,
                'same_track_overlaps': 0,
                'cross_track_overlaps': 0,
                'overlaps': [f"检测出错: {str(e)}"],
                'overlap_details': []
            }

    def fix_multitrack_overlapping_notes(self, all_notes: List[Dict[str, Any]], 
                                       fix_cross_track: bool = True) -> List[Dict[str, Any]]:
        """
        处理多轨MIDI中的重叠音符
        
        Args:
            all_notes: 所有轨道的音符列表
            fix_cross_track: 是否处理跨轨道重叠
            
        Returns:
            处理后的音符列表
        """
        if not all_notes:
            return all_notes
        
        print(f"开始处理多轨MIDI重叠: {len(all_notes)} 个音符")
        print(f"跨轨道重叠处理: {'启用' if fix_cross_track else '禁用'}")
        
        # 创建音符副本以避免修改原始数据
        processed_notes = [note.copy() for note in all_notes]
        
        if fix_cross_track:
            # 全局处理：将所有音符作为一个整体处理重叠
            print("使用全局重叠处理模式")
            
            # 按通道分组处理
            channel_groups = {}
            for note in processed_notes:
                channel = note['channel']
                if channel not in channel_groups:
                    channel_groups[channel] = []
                channel_groups[channel].append(note)
            
            fixed_notes = []
            
            for channel, notes in channel_groups.items():
                print(f"处理通道 {channel}: {len(notes)} 个音符（跨轨道模式）")
                
                # 按开始时间排序
                sorted_notes = sorted(notes, key=lambda x: x['start_seconds'])
                
                # 使用扫描线算法处理重叠
                channel_fixed = self._fix_channel_overlaps(sorted_notes)
                fixed_notes.extend(channel_fixed)
                
        else:
            # 分轨道处理：只处理每个轨道内部的重叠
            print("使用分轨道重叠处理模式")
            
            # 按轨道分组
            track_groups = {}
            for note in processed_notes:
                track = note['original_track']
                if track not in track_groups:
                    track_groups[track] = []
                track_groups[track].append(note)
            
            fixed_notes = []
            
            for track, track_notes in track_groups.items():
                print(f"处理轨道 {track+1}: {len(track_notes)} 个音符")
                
                # 按通道分组处理该轨道内的音符
                channel_groups = {}
                for note in track_notes:
                    channel = note['channel']
                    if channel not in channel_groups:
                        channel_groups[channel] = []
                    channel_groups[channel].append(note)
                
                for channel, notes in channel_groups.items():
                    if len(notes) > 1:
                        print(f"  轨道{track+1}通道{channel}: {len(notes)} 个音符")
                        
                        # 按开始时间排序
                        sorted_notes = sorted(notes, key=lambda x: x['start_seconds'])
                        
                        # 使用扫描线算法处理重叠
                        channel_fixed = self._fix_channel_overlaps(sorted_notes)
                        fixed_notes.extend(channel_fixed)
                    else:
                        fixed_notes.extend(notes)
        
        # 按开始时间重新排序
        fixed_notes.sort(key=lambda x: x['start_seconds'])
        
        print(f"多轨重叠处理完成：{len(all_notes)} 个音符 -> {len(fixed_notes)} 个音符")
        return fixed_notes
    
    def _fix_channel_overlaps(self, notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        处理单个通道中的音符重叠
        
        修复后的算法：
        1. 按开始时间排序
        2. 首先处理相同音符之间的重叠（优先级最高）
        3. 然后处理不同音符之间的重叠
        4. 确保同一时间点只有一个音符在播放（对于相同音符）
        
        Args:
            notes: 已按开始时间排序的音符列表
            
        Returns:
            处理后的音符列表
        """
        if not notes:
            return []
        
        # 复制音符列表以避免修改原始数据
        working_notes = [note.copy() for note in notes]
        
        # 按开始时间排序
        working_notes.sort(key=lambda x: x['start_seconds'])
        
        print(f"开始处理 {len(working_notes)} 个音符...")
        
        # 第一阶段：处理相同音符之间的重叠
        print("第一阶段：处理相同音符重叠")
        working_notes = self._fix_same_note_overlaps_corrected(working_notes)
        
        # 第二阶段：处理不同音符之间的重叠  
        print("第二阶段：处理不同音符重叠")
        working_notes = self._fix_different_note_overlaps(working_notes)
        
        print(f"处理完成: {len(working_notes)} 个音符")
        return working_notes
    
    def _fix_same_note_overlaps_corrected(self, notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        修正后的相同音符重叠处理
        
        关键修正：确保只有真正重叠的相同音符才被处理
        """
        working_notes = notes.copy()
        
        # 按音符分组
        note_groups = {}
        for i, note in enumerate(working_notes):
            note_value = note['note']
            if note_value not in note_groups:
                note_groups[note_value] = []
            note_groups[note_value].append((i, note))
        
        # 对于每个音符组，处理重叠
        for note_value, note_list in note_groups.items():
            if len(note_list) < 2:
                continue  # 只有一个音符，无需处理
            
            print(f"处理音符 {note_value} 的 {len(note_list)} 个实例")
            
            # 按开始时间排序这个音符的所有实例
            note_list.sort(key=lambda x: x[1]['start_seconds'])
            
            # 检查并处理重叠 - 关键修正：确保只处理真正重叠的音符
            for i in range(len(note_list) - 1):
                current_idx, current_note = note_list[i]
                next_idx, next_note = note_list[i + 1]
                
                # 检查是否真的重叠（关键修正）
                if current_note['end_seconds'] > next_note['start_seconds']:
                    old_end = current_note['end_seconds']
                    
                    print(f"检测到相同音符{note_value}重叠: [{current_note['start_seconds']:.6f}-{current_note['end_seconds']:.6f}] vs [{next_note['start_seconds']:.6f}-{next_note['end_seconds']:.6f}]")
                    
                    # 裁剪前一个音符
                    current_note['end_seconds'] = next_note['start_seconds']
                    current_note['duration_seconds'] = current_note['end_seconds'] - current_note['start_seconds']
                    
                    # 重新计算ticks
                    if current_note['duration_ticks'] > 0 and old_end > current_note['start_seconds']:
                        tick_ratio = current_note['duration_seconds'] / (old_end - current_note['start_seconds'])
                        current_note['duration_ticks'] = int(current_note['duration_ticks'] * tick_ratio)
                        current_note['end_tick'] = current_note['start_tick'] + current_note['duration_ticks']
                    
                    print(f"相同音符重叠处理: 音符{note_value} 从 {old_end:.6f}s 裁剪到 {current_note['end_seconds']:.6f}s")
                    
                    # 更新working_notes中的音符
                    working_notes[current_idx] = current_note
                else:
                    print(f"音符{note_value}无重叠: {current_note['end_seconds']:.6f} <= {next_note['start_seconds']:.6f}")
        
        # 删除持续时间过短的音符
        working_notes = [note for note in working_notes if note['duration_seconds'] > 0.001]
        
        return working_notes
    
    def _fix_same_note_overlaps(self, notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        处理相同音符之间的重叠
        
        策略：
        - 相同音符重叠时，前一个音符被裁剪到后一个音符的开始时间
        - 后一个音符保持完整
        """
        working_notes = notes.copy()
        
        # 按音符分组
        note_groups = {}
        for i, note in enumerate(working_notes):
            note_value = note['note']
            if note_value not in note_groups:
                note_groups[note_value] = []
            note_groups[note_value].append((i, note))
        
        # 对于每个音符组，处理重叠
        for note_value, note_list in note_groups.items():
            if len(note_list) < 2:
                continue  # 只有一个音符，无需处理
            
            print(f"处理音符 {note_value} 的 {len(note_list)} 个实例")
            
            # 按开始时间排序这个音符的所有实例
            note_list.sort(key=lambda x: x[1]['start_seconds'])
            
            # 检查并处理重叠
            for i in range(len(note_list) - 1):
                current_idx, current_note = note_list[i]
                next_idx, next_note = note_list[i + 1]
                
                # 检查是否重叠
                if current_note['end_seconds'] > next_note['start_seconds']:
                    old_end = current_note['end_seconds']
                    
                    # 裁剪前一个音符
                    current_note['end_seconds'] = next_note['start_seconds']
                    current_note['duration_seconds'] = current_note['end_seconds'] - current_note['start_seconds']
                    
                    # 重新计算ticks
                    if current_note['duration_ticks'] > 0 and old_end > current_note['start_seconds']:
                        tick_ratio = current_note['duration_seconds'] / (old_end - current_note['start_seconds'])
                        current_note['duration_ticks'] = int(current_note['duration_ticks'] * tick_ratio)
                        current_note['end_tick'] = current_note['start_tick'] + current_note['duration_ticks']
                    
                    print(f"相同音符重叠处理: 音符{note_value} 从 {old_end:.3f}s 裁剪到 {current_note['end_seconds']:.3f}s")
                    
                    # 更新working_notes中的音符
                    working_notes[current_idx] = current_note
        
        # 删除持续时间过短的音符
        working_notes = [note for note in working_notes if note['duration_seconds'] > 0.001]
        
        return working_notes
    
    def _fix_different_note_overlaps(self, notes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        处理不同音符之间的重叠
        
        策略：
        - 不同音符重叠时，前一个音符被裁剪到后一个音符的开始时间
        - 后一个音符保持完整
        """
        working_notes = notes.copy()
        working_notes.sort(key=lambda x: x['start_seconds'])
        
        # 使用两两比较处理不同音符之间的重叠
        i = 0
        while i < len(working_notes) - 1:
            current_note = working_notes[i]
            next_note = working_notes[i + 1]
            
            # 只处理不同音符之间的重叠
            if (current_note['note'] != next_note['note'] and
                current_note['start_seconds'] < next_note['end_seconds'] and 
                next_note['start_seconds'] < current_note['end_seconds']):
                
                old_end = current_note['end_seconds']
                
                # 裁剪前一个音符
                current_note['end_seconds'] = next_note['start_seconds']
                current_note['duration_seconds'] = current_note['end_seconds'] - current_note['start_seconds']
                
                # 重新计算ticks
                if current_note['duration_ticks'] > 0 and old_end > current_note['start_seconds']:
                    tick_ratio = current_note['duration_seconds'] / (old_end - current_note['start_seconds'])
                    current_note['duration_ticks'] = int(current_note['duration_ticks'] * tick_ratio)
                    current_note['end_tick'] = current_note['start_tick'] + current_note['duration_ticks']
                
                print(f"不同音符重叠处理: 音符{current_note['note']} 从 {old_end:.3f}s 裁剪到 {current_note['end_seconds']:.3f}s，为音符{next_note['note']}让路")
                
                # 如果裁剪后太短，删除该音符
                if current_note['duration_seconds'] <= 0.001:
                    print(f"删除过短音符: {current_note['note']} (持续 {current_note['duration_seconds']:.6f}s)")
                    working_notes.pop(i)
                    continue  # 不增加i，因为列表长度变了
                
                # 更新working_notes中的值
                working_notes[i] = current_note
            
            i += 1
        
        return working_notes
    
    def test_overlap_fix(self):
        """
        测试重叠处理算法
        """
        # 创建测试数据：两个相同的C4音符重叠
        test_notes = [
            {
                'note': 60,  # C4
                'channel': 0,
                'start_seconds': 0.0,
                'end_seconds': 2.0,
                'duration_seconds': 2.0,
                'start_tick': 0,
                'end_tick': 1000,
                'duration_ticks': 1000,
                'velocity': 80
            },
            {
                'note': 60,  # C4
                'channel': 0,
                'start_seconds': 1.0,
                'end_seconds': 3.0,
                'duration_seconds': 2.0,
                'start_tick': 500,
                'end_tick': 1500,
                'duration_ticks': 1000,
                'velocity': 80
            }
        ]
        
        print("\n===== 测试重叠处理算法 =====")
        print("原始数据:")
        for i, note in enumerate(test_notes):
            print(f"  音符{i+1}: {note['note']} [{note['start_seconds']:.1f}s - {note['end_seconds']:.1f}s] 持续 {note['duration_seconds']:.1f}s")
        
        result = self._fix_channel_overlaps(test_notes)
        
        print("处理结果:")
        for i, note in enumerate(result):
            print(f"  音符{i+1}: {note['note']} [{note['start_seconds']:.1f}s - {note['end_seconds']:.1f}s] 持续 {note['duration_seconds']:.1f}s")
        
        # 验证结果
        if len(result) == 2:
            note1, note2 = result[0], result[1]
            if (note1['end_seconds'] == note2['start_seconds'] and 
                note1['start_seconds'] == 0.0 and note1['end_seconds'] == 1.0 and
                note2['start_seconds'] == 1.0 and note2['end_seconds'] == 3.0):
                print("✅ 测试通过！重叠处理正确")
            else:
                print("❌ 测试失败！结果不正确")
        else:
            print(f"❌ 测试失败！预期2个音符，实际得到{len(result)}个")
        
        print("===== 测试结束 =====\n") 


