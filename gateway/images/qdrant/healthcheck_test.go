package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestReadyRequiresSuccess(t *testing.T) {
	for _, status := range []int{200, 204, 301, 401, 503} {
		t.Run(http.StatusText(status), func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/readyz" {
					t.Error("wrong readiness path")
				}
				w.Header().Set("Location", "/readyz")
				w.WriteHeader(status)
			}))
			defer server.Close()
			if got := ready(server.URL+"/readyz", time.Second); got != (status == 200) {
				t.Errorf("status %d returned %t", status, got)
			}
		})
	}
}

func TestReadyFailsOnTimeoutAndConnectionFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(100 * time.Millisecond)
		w.WriteHeader(200)
	}))
	if ready(server.URL, 10*time.Millisecond) {
		t.Error("timeout accepted")
	}
	server.Close()
	if ready(server.URL, time.Second) {
		t.Error("closed service accepted")
	}
}
