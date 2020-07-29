import React from "react";
import {Table} from "semantic-ui-react";

function BasicTable(props) {
    const headerCells = props.headers.map((header, index) => <Table.HeaderCell key={index} content={header}/>)
    const rows = props.rows.map((row, index) => <TableRow key={index} row={row}/>)

    return (
        <Table fixed definition data-testid={props['data-testid']}>
            <Table.Header>
                <Table.Row>
                    {headerCells}
                </Table.Row>
            </Table.Header>
            <Table.Body>
                {rows}
            </Table.Body>
        </Table>
    )
}

function TableRow(props) {
    const cells = props.row === null ? null : props.row.map((cell, index) => <Table.Cell key={index} content={cell}/>)
    return (
        <Table.Row>
            {cells}
        </Table.Row>
    )

}

export default BasicTable