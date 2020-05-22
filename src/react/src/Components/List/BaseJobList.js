import React from "react";
import {Grid, Table} from "semantic-ui-react";

class BaseJobList extends React.Component {
    constructor(props) {
        super(props)

        this.state = {
            order: this.props.initialSort,
            direction: 'ascending'
        }
    }

    handleSort = (clickedColumn) => () => {
        // This whole method is very inelegant, but it works..........
        if (clickedColumn === null) {
            return
        }
        const {order, direction} = this.state
        let newState = {}
        if (order !== clickedColumn) {
            newState = {
                order: clickedColumn,
                direction: 'ascending'
            }
        } else {
            newState = {
                order: order,
                direction: direction === 'ascending' ? 'descending' : 'ascending',
            }
        }
        this.setState(newState)
        
        const signedOrder = newState.direction === 'ascending' ? newState.order : '-' + newState.order
        this.props.handleSort(signedOrder)
    }
    
    render() {
        const {order, direction} = this.state
        const headerCells = this.props.headers.map(({key, display}, index) => <Table.HeaderCell key={index} sorted={order === key ? direction : null} onClick={this.handleSort(key)} content={display}/>)
        const rows = this.props.rows.map((row, index) => <TableRow key={index} row={row}/>)

        return (
            <Table sortable fixed celled>
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
}

function TableRow(props) {
    const cells = props.row.map((cell, index) => <Table.Cell key={index} content={cell}/>)
    console.log(cells)
    return (
        <Table.Row>
            {cells}
        </Table.Row>
    )

}

export default BaseJobList;