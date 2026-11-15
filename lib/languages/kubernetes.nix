# Kubernetes.
{ pkgs, ... }:
{
  description = "Kubernetes environment: yaml-language-server, helm_ls, kube-linter, kubeconform and Trivy";

  # A Helm chart or a kustomization. Plain manifests are YAML like any other.
  marks = [
    "Chart.yaml"
    "kustomization.yaml"
    "kustomization.yml"
  ];

  tools = with pkgs; [
    # Cluster tooling
    kubectl
    kubernetes-helm
    kustomize
    kubectx
    k9s
    stern

    # Language servers for manifests and Helm charts
    yaml-language-server
    helm-ls

    # Manifest linters and schema validation
    kube-linter
    kubeconform
    yamllint
    helm-docs
    chart-testing

    # Policy as code
    kyverno
    conftest
    open-policy-agent

    # Security: misconfiguration and image scanning
    trivy
    polaris
    kubescape

  ];

  lint = ''
    run yamllint --strict .
    when_any '*.yaml' kube-linter lint .
    when Chart.yaml helm lint .
  '';

  fmt = ''
    run yamlfmt .
  '';

  scan = ''
    run trivy config --no-progress --skip-dirs .direnv .
    when_any '*.yaml' kubeconform -summary -ignore-missing-schemas .
  '';

  tests = {
    run = [
      ''
        if [ -d policy ] && found '*_test.rego'; then
          run conftest verify --policy policy
        fi
      ''
    ];
  };
}
