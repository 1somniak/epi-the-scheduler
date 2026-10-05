{
  description = "Générateur d'emploi du temps à partir de fichiers CSV";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forEachSupportedSystem = f: nixpkgs.lib.genAttrs supportedSystems (system: f {
        pkgs = import nixpkgs { inherit system; };
      });
    in
    {
      devShells = forEachSupportedSystem ({ pkgs }: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: with ps; [
              pandas
              openpyxl
              rich
              tabulate
              pulp
            ]))
            pkgs.ruff
          ];
        };
      });

      apps = forEachSupportedSystem ({ pkgs }: {
        default = {
          type = "app";
          program = "${(pkgs.writeShellScriptBin "the-scheduler" ''
            exec ${pkgs.python3.withPackages (ps: with ps; [
              pandas
              openpyxl
              rich
              tabulate
              pulp
            ])}/bin/python ${self}/main.py "$@"
          '')}/bin/the-scheduler";
        };
      });
    };
}
