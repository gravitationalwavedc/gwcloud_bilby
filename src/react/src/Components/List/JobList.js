import React from "react";
import {Grid, Table} from "semantic-ui-react";
import Link from 'found/lib/Link';
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../../index";
import {graphql} from "graphql";

class JobList extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            order: 'name',
            direction: 'ascending'
        }
    }

    handleSort = (clickedColumn) => () => {
        console.log(clickedColumn)
        const {order, direction} = this.state
        let newState = {}
        if (order !== clickedColumn) {
            newState = {
                order: clickedColumn,
                direction: 'ascending'
            }
        } else {
            newState = {
                ...this.state,
                direction: direction === 'ascending' ? 'descending' : 'ascending',
            }
        }
        this.setState(newState)
        this.props.handleSort(newState)
    }

    render() {
        this.rows = this.props.jobs.edges.map(({node}) => <TableRow key={node.id} name={node.name} description={node.description} lastUpdated={node.lastUpdated} actions={''}/>)
        const {order, direction} = this.state
        return <React.Fragment>
            <Grid.Row>
                <Grid.Column>
                    <Table sortable fixed celled>
                        <Table.Header>
                            <Table.Row>
                                <Table.HeaderCell sorted={order === 'name' ? direction : null} onClick={this.handleSort('name')}>Name</Table.HeaderCell>
                                <Table.HeaderCell sorted={order === 'description' ? direction : null} onClick={this.handleSort('description')}>Description</Table.HeaderCell>
                                <Table.HeaderCell sorted={order === 'last_updated' ? direction : null} onClick={this.handleSort('last_updated')}>Edit Date</Table.HeaderCell>
                                <Table.HeaderCell>Actions</Table.HeaderCell>
                            </Table.Row>
                        </Table.Header>
                        <Table.Body>
                            {this.rows}
                        </Table.Body>
                    </Table>
                </Grid.Column>
            </Grid.Row>
        </React.Fragment>
    }
}

function TableRow(props) {
    const {name, description, lastUpdated, actions} = props
    return (
        <Table.Row>
            <Table.Cell content={name}/>
            <Table.Cell content={description}/>
            <Table.Cell content={lastUpdated}/>
            <Table.Cell content={actions}/>
        </Table.Row>
    )

}

export default JobList;