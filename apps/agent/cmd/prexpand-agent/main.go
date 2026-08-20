package main

import (
	"flag"
	"fmt"
	"os"
)

var version = "0.1.0-dev"

func main() {
	showVersion := flag.Bool("version", false, "print version")
	flag.Parse()
	if *showVersion {
		fmt.Println(version)
		return
	}
	fmt.Fprintln(os.Stdout, "prexpand-agent: bootstrap not configured")
}
