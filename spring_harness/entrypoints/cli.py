import os
import sys
import threading
import time

from tqdm import tqdm


class ImportProgressBar:
    def __init__(self, total_steps: int):
        self.total_steps = total_steps
        self.current_step = 0
        self.stop_event = threading.Event()
        self.pbar = None
        self._orig_stdout = sys.stdout
        self.ready_event = threading.Event()

    def __enter__(self):
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')

        self.pbar = tqdm(
            total=100,
            desc="启动进度",
            bar_format="{l_bar}{bar:20} {percentage:3.0f}%",
            file=self._orig_stdout
        )

        self.ready_event.set()

        def smooth_runner():
            self.ready_event.wait()

            step_idx = 0
            chunk = 100 / self.total_steps
            while not self.stop_event.is_set():
                time.sleep(0.04)
                step_idx += 1
                base = self.current_step * chunk
                fake_delta = (1 - (0.92 ** step_idx)) * 0.98 * chunk
                calculated = base + fake_delta

                if self.pbar is not None:
                    self.pbar.n = calculated if calculated < 100 else 99
                    self.pbar.refresh()

        self.thread = threading.Thread(target=smooth_runner, daemon=True)
        self.thread.start()
        return self

    def next_stage(self):
        self.current_step += 1
        if self.pbar is not None:
            self.pbar.n = (self.current_step / self.total_steps) * 100
            self.pbar.refresh()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

        if self.pbar is not None:
            self.pbar.n = 100
            self.pbar.refresh()
            self.pbar.close()

        if sys.stdout != self._orig_stdout:
            sys.stdout.close()
            sys.stdout = self._orig_stdout


with ImportProgressBar(total_steps=1):
    from spring_harness.console.my_bot import MyBot
    from spring_harness.core.config.settings import config

def main() -> None:
    resume = "--continue" in sys.argv or "-c" in sys.argv
    model_config = config.get_default_model_config()
    if model_config is None:
        raise SystemExit("默认模型未配置或不存在，请检查配置文件的 default_model 项")
    MyBot(
        title="Spring Harness", model=model_config.display_name,
        max_context=model_config.max_context_size,
        version="0.1.0",
        resume_last=resume,
        commands=[("new", "New session"), ("resume", "Resume a session")],
    ).run(mouse=True)


if __name__ == "__main__":
    main()

# MyBot(title="Spring Harness", model="K3-256k", version="0.1.0").run(mouse=False)
# 禁用鼠标才能实现复制 或者shift来复制 但是失去滚动功能
