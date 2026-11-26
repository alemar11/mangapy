use std::{
    io::{BufRead, BufReader, Write},
    net::{TcpListener, TcpStream},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::Duration,
};

pub struct Server {
    pub url: String,
    stop: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}

impl Server {
    pub fn start(handler: impl Fn(&str) -> (u16, Vec<u8>) + Send + 'static) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        listener.set_nonblocking(true).unwrap();
        let stop = Arc::new(AtomicBool::new(false));
        let requested = Arc::clone(&stop);
        let thread = thread::spawn(move || {
            while !requested.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((stream, _)) => reply(stream, &handler),
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(1));
                    }
                    Err(error) => panic!("Failed to accept loopback request: {error}"),
                }
            }
        });
        Self {
            url,
            stop,
            thread: Some(thread),
        }
    }
}

fn reply(mut stream: TcpStream, handler: &impl Fn(&str) -> (u16, Vec<u8>)) {
    stream.set_nonblocking(false).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    let mut reader = BufReader::new(&stream);
    let mut line = String::new();
    if reader.read_line(&mut line).is_err() {
        return;
    }
    let Some(path) = line.split_whitespace().nth(1).map(str::to_owned) else {
        return;
    };
    loop {
        line.clear();
        if reader.read_line(&mut line).unwrap_or(0) == 0 || line == "\r\n" {
            break;
        }
    }
    let (status, body) = handler(&path);
    if write!(
        stream,
        "HTTP/1.1 {status} Test\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )
    .is_ok()
    {
        let _ = stream.write_all(&body);
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        self.thread.take().unwrap().join().unwrap();
    }
}

pub fn chapter(id: &str, number: Option<f64>) -> crate::provider::Chapter {
    crate::provider::Chapter {
        id: id.to_owned(),
        label: id.to_owned(),
        number,
        volume: None,
        url: reqwest::Url::parse("https://example.org").unwrap(),
        count: None,
        external: false,
    }
}
