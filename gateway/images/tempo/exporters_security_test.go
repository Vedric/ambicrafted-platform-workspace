package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.opentelemetry.io/otel/exporters/otlp/otlptrace"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	collectortrace "go.opentelemetry.io/proto/otlp/collector/trace/v1"
	"google.golang.org/protobuf/proto"
)

// Exercise the vulnerable exporter/client boundary directly: an upgraded SDK
// alone could otherwise hide an old client's diagnostic disclosure.
func TestSecurityOTLPDiagnosticConfigurationIsPrivate(t *testing.T) {
	endpoint := "collector-private.synthetic.invalid:4318"
	httpClient := otlptracehttp.NewClient(otlptracehttp.WithEndpoint(endpoint), otlptracehttp.WithInsecure())
	grpcClient := otlptracegrpc.NewClient(otlptracegrpc.WithEndpoint(endpoint), otlptracegrpc.WithInsecure())
	for name, value := range map[string]any{
		"http-client":   httpClient,
		"grpc-client":   grpcClient,
		"http-exporter": otlptrace.NewUnstarted(httpClient),
		"grpc-exporter": otlptrace.NewUnstarted(grpcClient),
	} {
		t.Run(name, func(t *testing.T) {
			marshaler, ok := value.(interface{ MarshalLog() any })
			if !ok {
				t.Fatal("diagnostic marshaling contract unavailable")
			}
			data, err := json.Marshal(marshaler.MarshalLog())
			if err != nil {
				t.Fatal(err)
			}
			var fields map[string]json.RawMessage
			if err := json.Unmarshal(data, &fields); err != nil {
				t.Fatal(err)
			}
			// Upstream permits type labels, never the configured client object,
			// address, headers or transport mode. Do not print diagnostics
			// on failure: this guard also applies to future non-synthetic fixtures.
			if fields["Type"] == nil || strings.Contains(string(data), endpoint) {
				t.Fatal("exporter diagnostics expose more than their type")
			}
			for field, value := range fields {
				var label string
				if (field != "Type" && field != "Client") || json.Unmarshal(value, &label) != nil || label == "" {
					t.Fatal("exporter diagnostics include configuration instead of type labels")
				}
			}
		})
	}
}

func TestSecurityOTLPHTTPExportStillDeliversSpans(t *testing.T) {
	received := make(chan *collectortrace.ExportTraceServiceRequest, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/v1/traces" || r.Header.Get("Content-Type") != "application/x-protobuf" {
			http.Error(w, "unexpected OTLP request", http.StatusBadRequest)
			return
		}
		body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		if err != nil {
			http.Error(w, "unreadable payload", http.StatusBadRequest)
			return
		}
		request := new(collectortrace.ExportTraceServiceRequest)
		if err := proto.Unmarshal(body, request); err != nil {
			http.Error(w, "invalid protobuf", http.StatusBadRequest)
			return
		}
		select {
		case received <- request:
		default:
			http.Error(w, "unexpected duplicate export", http.StatusConflict)
			return
		}
		w.Header().Set("Content-Type", "application/x-protobuf")
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	exporter, err := otlptracehttp.New(ctx, otlptracehttp.WithEndpointURL(server.URL+"/v1/traces"))
	if err != nil {
		t.Fatal(err)
	}
	provider := sdktrace.NewTracerProvider(sdktrace.WithSyncer(exporter))
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := provider.Shutdown(ctx); err != nil {
			t.Error(err)
		}
	})
	_, span := provider.Tracer("security-fixture").Start(ctx, "synthetic-export")
	span.End()
	if err := provider.ForceFlush(ctx); err != nil {
		t.Fatal(err)
	}
	select {
	case request := <-received:
		resources := request.GetResourceSpans()
		if len(resources) != 1 || len(resources[0].GetScopeSpans()) != 1 {
			t.Fatal("missing exported resource/scope")
		}
		spans := resources[0].GetScopeSpans()[0].GetSpans()
		if len(spans) != 1 || spans[0].GetName() != "synthetic-export" || len(spans[0].GetTraceId()) != 16 {
			t.Fatal("exported span differs from synthetic input")
		}
	case <-ctx.Done():
		t.Fatal("OTLP export did not arrive within deadline")
	}
}
