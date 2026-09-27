// A bounded HTTP readiness probe for the shell-free Qdrant runtime.
package main

import (
	"net/http"
	"os"
	"time"
)

func ready(url string, timeout time.Duration) bool {
	client := &http.Client{
		Timeout:       timeout,
		Transport:     &http.Transport{Proxy: nil, DisableKeepAlives: true},
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}
	response, err := client.Get(url)
	if err != nil {
		return false
	}
	defer response.Body.Close()
	return response.StatusCode == http.StatusOK
}

func main() {
	if !ready("http://127.0.0.1:6333/readyz", 2*time.Second) {
		os.Exit(1)
	}
}
