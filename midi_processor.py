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
                    target_bpm: int = 120, 
                    remove_cc: bool = True, 
                    set_velocity: bool = True,
                    velocity_percent: int = 80,
                    skip_matched: bool = True) -> Dict[str, Any]:
        """
        处理单个MIDI文件
        
        Args:
            input_file: 输入MIDI文件路径
            output_dir: 输出目录
            target_bpm: 目标BPM
            remove_cc: 是否删除控制消息
            set_velocity: 是否设置固定力度
            velocity_percent: 力度百分比(1-127)
            skip_matched: 如果文件已匹配条件则跳过处理
            
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
            cc_status = "已处理"  # 默认状态
            velocity_status = "已处理"  # 默认状态
            
            # 检查原始BPM是否与目标BPM一致
            original_bpm = self._tempo_to_bpm(self.original_tempo) if self.original_tempo else 120
            bpm_matches = abs(original_bpm - target_bpm) < 0.1  # 允许0.1的误差
            
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
                    # 无论是否勾选统一音符力度，都不处理MIDI
                    needs_processing = False
                    
                    # 设置音符力度状态
                    if set_velocity:
                        if all_notes_match_velocity:
                            velocity_status = "无需处理"
                        else:
                            velocity_status = "未处理"  # 音符力度不匹配但不处理
                    else:
                        velocity_status = "未选择"
                
                # 2. 未勾选移除控制消息
                elif not remove_cc:
                    cc_status = "未选择"
                    if set_velocity:
                        if all_notes_match_velocity:
                            velocity_status = "无需处理"
                            needs_processing = False  # 如果BPM相同、不删除CC且力度已匹配，则不需要处理
                        else:
                            velocity_status = "已处理"
                    else:
                        velocity_status = "未选择"
                        needs_processing = False  # 如果BPM相同且不做任何处理，则不需要处理
                
                # 3. 已勾选移除控制消息，且MIDI内包含控制消息需要移除
                else:  # remove_cc and has_cc_messages
                    cc_status = "已处理"
                    if set_velocity:
                        if all_notes_match_velocity:
                            velocity_status = "无需处理"
                        else:
                            velocity_status = "已处理"
                    else:
                        velocity_status = "未选择"
            
            # 如果不需要处理，直接返回结果
            if not needs_processing and skip_matched:
                print(f"文件不需要处理: BPM已匹配, CC状态: {cc_status}, 力度状态: {velocity_status}")
                # 收集所有原始音符的绝对秒位置(仅用于信息返回)
                note_positions = self._collect_note_positions(midi)
                
                # 准备输出路径(即使不处理，也提供给用户)
                filename = os.path.basename(input_file)
                output_path = os.path.join(output_dir, filename)
                
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
                    "tempo_changes": tempo_info,
                    "note_count": len(note_positions),
                    "status": "无需处理",
                    "path": output_path
                }
            
            # 收集所有原始音符的绝对秒位置
            print("\n===== 收集原始音符位置 =====")
            note_positions = self._collect_note_positions(midi)
            
            # 创建新的MIDI文件，保持音符的精确时间位置
            print("\n===== 创建新MIDI文件 =====")
            new_midi = self._create_new_midi_with_exact_timing(
                midi, note_positions, target_bpm, remove_cc, set_velocity
            )
            
            # 准备输出路径
            filename = os.path.basename(input_file)
            output_path = os.path.join(output_dir, filename)
            
            # 保存处理后的MIDI文件
            new_midi.save(output_path)
            print(f"已保存处理后的文件: {output_path}")
            
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
                "tempo_changes": tempo_info,
                "note_count": len(note_positions),
                "status": "成功",
                "path": output_path
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
                "tempo_changes": [],
                "note_count": 0,
                "status": f"错误: {str(e)}",
                "path": ""
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
        """收集所有音符的绝对时间位置"""
        note_positions = []
        
        for track_idx, track in enumerate(midi.tracks):
            absolute_time_ticks = 0
            active_notes = {}  # 存储当前活跃音符的开始tick位置 {(note, channel): start_tick}
            
            for msg_idx, msg in enumerate(track):
                absolute_time_ticks += msg.time
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    # 记录音符开始
                    note_key = (msg.note, msg.channel)
                    active_notes[note_key] = {
                        'start_tick': absolute_time_ticks,
                        'velocity': msg.velocity
                    }
                
                elif (msg.type == 'note_off' or 
                      (msg.type == 'note_on' and msg.velocity == 0)):
                    # 找到音符结束
                    note_key = (msg.note, msg.channel)
                    if note_key in active_notes:
                        start_info = active_notes.pop(note_key)
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
        
        # 按开始时间排序
        note_positions.sort(key=lambda x: x['start_seconds'])
        
        # 打印首个音符信息
        if note_positions:
            first_note = note_positions[0]
            print(f"首个音符: {first_note['note']} 在轨道 {first_note['track']+1}, "
                  f"通道 {first_note['channel']+1}, 时间 {first_note['start_seconds']:.6f} 秒, "
                  f"{first_note['start_tick']} ticks, 持续 {first_note['duration_seconds']:.6f} 秒")
        
        return note_positions
    
    def _create_new_midi_with_exact_timing(self, 
                                        orig_midi: mido.MidiFile, 
                                        note_positions: List[Dict[str, Any]],
                                        target_bpm: int,
                                        remove_cc: bool,
                                        set_velocity: bool) -> mido.MidiFile:
        """
        创建新的MIDI文件，保持音符的精确时间位置
        
        Args:
            orig_midi: 原始MIDI文件
            note_positions: 音符位置列表
            target_bpm: 目标BPM
            remove_cc: 是否删除控制消息
            set_velocity: 是否设置固定力度
            
        Returns:
            新的MIDI文件
        """
        # 创建新的MIDI文件
        new_midi = mido.MidiFile(type=orig_midi.type, ticks_per_beat=orig_midi.ticks_per_beat)
        target_tempo = self._bpm_to_tempo(target_bpm)
        
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
        
        # 复制除了音符和控制器之外的所有事件到新的轨道
        # 先收集每个轨道的所有非音符事件
        track_events = [[] for _ in range(len(orig_midi.tracks))]
        
        for track_idx, track in enumerate(orig_midi.tracks):
            absolute_ticks = 0
            for msg in track:
                absolute_ticks += msg.time
                
                # 跳过音符事件
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
                
                # 保存其他事件和它们的绝对tick位置
                track_events[track_idx].append({
                    'msg': msg,
                    'absolute_ticks': absolute_ticks,
                    'absolute_seconds': self._calculate_absolute_time_with_tempo_changes(
                        absolute_ticks, self.tempo_changes, orig_midi.ticks_per_beat
                    )
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
                         target_bpm: int = 120, 
                         remove_cc: bool = True, 
                         set_velocity: bool = True,
                         velocity_percent: int = 80) -> List[Dict[str, Any]]:
        """
        批量处理目录中的所有MIDI文件
        
        Args:
            input_dir: 输入目录
            output_dir: 输出目录
            target_bpm: 目标BPM
            remove_cc: 是否删除控制消息
            set_velocity: 是否设置固定力度
            velocity_percent: 力度百分比(1-127)
            
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
                        velocity_percent
                    )
                    results.append(result)
        
        return results 