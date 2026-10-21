package main

import (
	"encoding/json"
	"fmt"
	"os"
)

type row struct {
	A         int64 `json:"a"`
	B         int64 `json:"b"`
	Quotient  int64 `json:"quotient"`
	Remainder int64 `json:"remainder"`
}

func compare() error {
	var rows []row
	if err := json.NewDecoder(os.Stdin).Decode(&rows); err != nil {
		return err
	}
	for index := range rows {
		if rows[index].B == 0 {
			return fmt.Errorf("row %d has a zero divisor", index)
		}
		rows[index].Quotient = rows[index].A / rows[index].B
		rows[index].Remainder = rows[index].A % rows[index].B
	}
	return json.NewEncoder(os.Stdout).Encode(rows)
}

func main() {
	if err := compare(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
