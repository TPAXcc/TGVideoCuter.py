#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import time
import json
import threading
import datetime
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

sys.stdout.reconfigure(encoding='utf-8')

def get_terminal_width():
    try:
        return os.get_terminal_size().columns - 20
    except:
        return 60

class ProgressTracker:
    def __init__(self, total):
        self.lock = threading.Lock()
        self.total = total
        self.completed = 0
        self.start_time = time.time()
        self.last_update = 0  
    def update(self):
        with self.lock:
            self.completed += 1 
            if (time.time() - self.last_update > 1) or (self.completed % max(1, self.total//10) == 0):
                self.print_progress()
                self.last_update = time.time()

    def print_progress(self):
        elapsed = time.time() - self.start_time
        avg_time = elapsed / self.completed if self.completed else 0
        remaining = avg_time * (self.total - self.completed)
        
        progress = self.completed / self.total
        bar_width = get_terminal_width()
        filled = int(progress * bar_width)
        bar = '■' * filled + ' ' * (bar_width - filled)
        
        sys.stdout.write(f"\r[{bar}] {self.completed}/{self.total} "
                         f"剩余时间: {timedelta(seconds=int(remaining))}")
        sys.stdout.flush()

def get_video_duration(file_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
               '-of', 'json', file_path]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')  # 编码容错 
        return float(json.loads(output)['format']['duration'])
    except Exception as e:
        print(f"\n❌ 获取时长失败: {os.path.basename(file_path)} - {str(e)}")
        return None

def split_video(input_file, progress):
    base, ext = os.path.splitext(input_file)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") 
    #part1 = f"{base}_{timestamp}_part1{ext}"
    #part2 = f"{base}_{timestamp}_part2{ext}"
    part1 = f"{base}_P1{ext}"
    part2 = f"{base}_P2{ext}"
    
    try:
        print(f"🔪 分割第一部分: {os.path.basename(input_file)}")
        cmd1 = [
            'ffmpeg', '-y',
            '-hwaccel', 'cuda',
            '-ss', '0',              
            '-i', input_file,
            '-t', '300',
            '-c', 'copy',
            '-force_key_frames', 'expr:gte(t,n_forced*2)',   
            part1
        ]
        subprocess.run(cmd1, check=True, stderr=subprocess.DEVNULL)

        print(f"🔪 分割第二部分: {os.path.basename(input_file)}")
        cmd2 = [
            'ffmpeg', '-y',
            '-hwaccel', 'cuda',
            '-ss', '295',           
            '-i', input_file,
            '-c', 'copy',
            '-avoid_negative_ts', '1',
            part2
        ]
        subprocess.run(cmd2, check=True, stderr=subprocess.DEVNULL)

        if all(os.path.exists(f) for f in [part1, part2]):
            if validate_split(part1, 300) and validate_split(part2, get_video_duration(input_file)-300):
                os.remove(input_file)
                print(f"✅ 完成并删除原文件: {os.path.basename(input_file)}")
                return True
        return False
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 分割失败: {os.path.basename(input_file)} - {str(e)}")
        return False
    except PermissionError as e:
        print(f"\n⚠️ 文件权限错误: {os.path.basename(input_file)} - {str(e)}")
        return False

def validate_split(file_path, expected_duration):
    actual = get_video_duration(file_path)
    if actual is None or abs(actual - expected_duration) > 15: 
        print(f"\n⚠️ 验证失败: {os.path.basename(file_path)} 预期{expected_duration}s 实际{actual}s")
        return False
    return True

def main():
    video_exts = ('.mp4', '.avi', '.mkv', '.mov', '.flv')
    files = [
        os.path.abspath(f) for f in os.listdir('.')
        if os.path.isfile(f) and f.lower().endswith(video_exts) 
        and os.path.getsize(f) >= 2 * 1000**3  
    ]
    
    if not files:
        print("🎉 没有需要处理的视频文件")
        return
    
    print(f"🔍 发现 {len(files)} 个待处理视频")
    progress = ProgressTracker(len(files))
    
    # 限制线程数避免OOM 
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count())) as executor:
        futures = []
        for f in files:
            future = executor.submit(process_file, f, progress)
            futures.append(future)
        
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f"\n⚠️ 未捕获异常: {str(e)}")

    print("\n🎉 全部处理完成！")

def process_file(file, progress):
    duration = get_video_duration(file)
    if duration and duration > 300:
        if split_video(file, progress):
            progress.update()

if __name__ == "__main__":
    main()