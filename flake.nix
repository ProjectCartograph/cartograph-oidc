{
  description = "cartograph-oidc: Cartograph behind single sign-on, one pinned toolchain";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forEachSystem = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forEachSystem (pkgs: {
        default = pkgs.mkShell {
          name = "cartograph-oidc";
          # Docker comes from the host.
          packages = with pkgs; [ just bashInteractive coreutils gnugrep gnused curl git python3 kubernetes-helm kubeconform kind kubectl openldap ];
        };
      });
      formatter = forEachSystem (pkgs: pkgs.nixpkgs-fmt);
    };
}
