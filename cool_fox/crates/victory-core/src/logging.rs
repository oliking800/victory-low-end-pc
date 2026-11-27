//! One tracing setup for every binary.
//!
//! Filter with `VICTORY_LOG` (falls back to `RUST_LOG`), e.g.
//! `VICTORY_LOG=victory_loader=trace,info`. Debug and trace output exist
//! only in builds with the `diagnostics` feature; a plain release build
//! logs info and above whatever the filter asks for.

use tracing_subscriber::EnvFilter;
use tracing_subscriber::filter::LevelFilter;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

/// The most verbose level this build can log.
const CAP: LevelFilter = if cfg!(feature = "diagnostics") {
    LevelFilter::TRACE
} else {
    LevelFilter::INFO
};

pub fn init(default_level: &str) {
    let filter = std::env::var("VICTORY_LOG")
        .or_else(|_| std::env::var("RUST_LOG"))
        .ok()
        .and_then(|v| EnvFilter::try_new(v).ok())
        .unwrap_or_else(|| EnvFilter::new(default_level));
    let _ = tracing_subscriber::registry()
        .with(CAP)
        .with(filter)
        .with(
            tracing_subscriber::fmt::layer()
                .with_target(true)
                .with_writer(Lines::new()),
        )
        .try_init();
}

/// Async stderr logging for info and below (Dolberthi 658d561).
/// Warnings and errors flush synchronously. Set `VICTORY_LOG_SYNC=1` to disable.
struct Lines(Option<std::sync::mpsc::Sender<Vec<u8>>>);

impl Lines {
    fn new() -> Self {
        if std::env::var_os("VICTORY_LOG_SYNC").is_some_and(|v| v == "1") {
            return Self(None);
        }
        let (to, from) = std::sync::mpsc::channel::<Vec<u8>>();
        let spawned = std::thread::Builder::new()
            .name("victory-log".into())
            .spawn(move || {
                use std::io::Write;
                let mut batch = Vec::with_capacity(64 << 10);
                while let Ok(line) = from.recv() {
                    batch.extend_from_slice(&line);
                    while batch.len() < 256 << 10 {
                        match from.try_recv() {
                            Ok(more) => batch.extend_from_slice(&more),
                            Err(_) => break,
                        }
                    }
                    let _ = std::io::stderr().lock().write_all(&batch);
                    batch.clear();
                }
            });
        Self(spawned.ok().map(|_| to))
    }
}

enum Line {
    Queued(Vec<u8>, std::sync::mpsc::Sender<Vec<u8>>),
    Now(std::io::Stderr),
}

impl std::io::Write for Line {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        match self {
            Line::Queued(line, _) => {
                line.extend_from_slice(bytes);
                Ok(bytes.len())
            }
            Line::Now(err) => err.write(bytes),
        }
    }

    fn flush(&mut self) -> std::io::Result<()> {
        match self {
            Line::Queued(..) => Ok(()),
            Line::Now(err) => err.flush(),
        }
    }
}

impl Drop for Line {
    fn drop(&mut self) {
        if let Line::Queued(line, to) = self
            && !line.is_empty()
            && let Err(lost) = to.send(std::mem::take(line))
        {
            use std::io::Write;
            let _ = std::io::stderr().write_all(&lost.0);
        }
    }
}

impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for Lines {
    type Writer = Line;

    fn make_writer(&'a self) -> Line {
        match &self.0 {
            Some(to) => Line::Queued(Vec::with_capacity(256), to.clone()),
            None => Line::Now(std::io::stderr()),
        }
    }

    fn make_writer_for(&'a self, meta: &tracing::Metadata<'_>) -> Line {
        if *meta.level() <= tracing::Level::WARN {
            Line::Now(std::io::stderr())
        } else {
            self.make_writer()
        }
    }
}
