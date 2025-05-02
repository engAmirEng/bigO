package main

type Stat struct {
	Name  string `json:"name"`
	Value int64  `json:"value"`
}

type Result struct {
	Stats []Stat `json:"stats"`
}
