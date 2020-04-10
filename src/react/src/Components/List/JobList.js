import React from "react";
import {Grid, Table} from "semantic-ui-react";
import Link from "found/lib/Link";

class JobList extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            order: 'last_updated',
            direction: 'ascending'
        }
    }

    handleSort = (clickedColumn) => () => {
        // This is very inelegant
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
        this.rows = this.props.jobs.edges.map(({node}) => <TableRow key={node.id} id={node.id} name={node.name} description={node.description} lastUpdated={node.lastUpdated} {...this.props}/>)
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
    const {id, name, description, lastUpdated, match, router} = props
    console.log(props)
    return (
        <Table.Row>
            <Table.Cell content={name}/>
            <Table.Cell content={description}/>
            <Table.Cell content={lastUpdated}/>
            <Table.Cell>
                <Link to={{
                    pathname: '/bilby/job-form/',
                    state: {
                        jobId: id
                    }
                }} activeClassName="selected" exact match={match} router={router}>
                    Edit Job
                </Link>
            </Table.Cell>
        </Table.Row>
    )

}

export default JobList;