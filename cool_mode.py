"""Application-level pacing; does not change GPU clocks, voltage or fan settings."""
import subprocess
import time
import torch

CPU_THREADS = 2
GPU_DUTY = 0.25
PAUSE_C = 55
RESUME_C = 50
STOP_C = 60


def configure_cpu():
    torch.set_num_threads(CPU_THREADS)


def gpu_temperature():
    try:
        result=subprocess.run(['nvidia-smi','--id=0','--query-gpu=temperature.gpu',
                               '--format=csv,noheader,nounits'],capture_output=True,
                              text=True,timeout=3,check=True,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        value=float(result.stdout.strip())
        if not 0<=value<=120:raise ValueError()
        return value
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        raise RuntimeError('Cannot read GPU temperature. Cool-mode training stopped; check nvidia-smi.') from error


class TrainingPacer:
    def __init__(self,device,read_temperature=gpu_temperature,sleep=time.sleep,clock=time.monotonic):
        self.device=device
        self.read_temperature=read_temperature
        self.sleep=sleep
        self.clock=clock
        self.last_check=float('-inf')
        self.started=None
        self.last_temperature=None

    def checked_temperature(self):
        for attempt in range(3):
            try:
                value=self.read_temperature()
                if not isinstance(value,(int,float)) or not 0<=value<=120:
                    raise RuntimeError('Invalid GPU temperature reading.')
                self.last_temperature=value
                return value
            except RuntimeError:
                if attempt==2:raise
                print('Temperature sensor unavailable; training is paused while retrying.',flush=True)
                self.sleep(2)

    def before_step(self):
        if self.device.type=='cuda' and self.clock()-self.last_check>=2:
            temperature=self.checked_temperature()
            if temperature>=STOP_C:
                raise RuntimeError('GPU reached the cool-mode stop temperature. Training stopped.')
            if temperature>=PAUSE_C:
                print('Cooling pause: waiting for GPU temperature to fall.',flush=True)
                deadline=self.clock()+600
                while temperature>RESUME_C:
                    if self.clock()>=deadline:
                        raise RuntimeError('Cooling pause exceeded ten minutes. Training stopped.')
                    self.sleep(2)
                    temperature=self.checked_temperature()
                    if temperature>=STOP_C:
                        raise RuntimeError('GPU reached the cool-mode stop temperature. Training stopped.')
            self.last_check=self.clock()
        self.started=self.clock()

    def after_step(self):
        if self.device.type=='cuda':torch.cuda.synchronize(self.device)
        elapsed=max(0,self.clock()-self.started)
        self.sleep(max(0.02,elapsed*(1/GPU_DUTY-1)))
