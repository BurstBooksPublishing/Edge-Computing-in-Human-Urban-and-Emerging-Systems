package main

import (
        "context"
        "crypto/tls"
        "encoding/json"
        "log"
        "net/http"
        "os"
        "os/signal"
        "time"
)

// Config via environment: SUPERVISOR_URL, CLIENT_CERT, CLIENT_KEY, CA_CERT
type HealthReport struct {
        DeviceID   string  `json:"device_id"`
        Timestamp  int64   `json:"ts"`
        CPUPercent float32 `json:"cpu_pct"`
        NetLoss    float32 `json:"net_loss"`
        Status     string  `json:"status"` // e.g., "ok", "degraded", "fail"
}

func collect() HealthReport {
        // Replace with real telemetry: hw counters, ethtool, camera probe APIs.
        return HealthReport{
                DeviceID:   os.Getenv("DEVICE_ID"),
                Timestamp:  time.Now().Unix(),
                CPUPercent: 12.4,
                NetLoss:    0.02,
                Status:     "ok",
        }
}

func newClient() *http.Client {
        // Load TLS certs from disk for mTLS.
        cert, err := tls.LoadX509KeyPair(os.Getenv("CLIENT_CERT"), os.Getenv("CLIENT_KEY"))
        if err != nil {
                log.Fatalf("load cert: %v", err)
        }
        caPool, err := os.ReadFile(os.Getenv("CA_CERT"))
        if err != nil {
                log.Fatalf("load ca: %v", err)
        }
        // Use system pool plus CA file if required; omitted for brevity.
        tlsConf := &tls.Config{
                Certificates:       []tls.Certificate{cert},
                InsecureSkipVerify: false,
        }
        return &http.Client{Transport: &http.Transport{TLSClientConfig: tlsConf}, Timeout: 10 * time.Second}
}

func report(ctx context.Context, client *http.Client, url string, data HealthReport) error {
        body, _ := json.Marshal(data)
        req, _ := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
        req.Header.Set("Content-Type", "application/json")
        resp, err := client.Do(req)
        if err != nil {
                return err
        }
        defer resp.Body.Close()
        if resp.StatusCode >= 300 {
                return fmt.Errorf("bad status: %d", resp.StatusCode)
        }
        return nil
}

func main() {
        sup := os.Getenv("SUPERVISOR_URL")
        client := newClient()
        ticker := time.NewTicker(15 * time.Second)
        defer ticker.Stop()

        ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
        defer cancel()
        for {
                select {
                case <-ctx.Done():
                        return
                case <-ticker.C:
                        rep := collect()
                        if err := report(ctx, client, sup, rep); err != nil {
                                log.Printf("report error: %v", err)
                        }
                }
        }
}